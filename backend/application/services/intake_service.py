"""Orquestación del intake de facturas (capa de aplicación).

Une las piezas YA EXISTENTES sin duplicarlas:
  · clasificador_factura.clasificar_email  → es factura / no_factura / portal
  · extract_service.extraer_desde_pdf      → pipeline OCR 2-etapas
  · invoice_validator.validar              → punto único de validación (con suplido)
  · proveedor_resolver.resolver_proveedor  → identidad por CIF (sin duplicados)
  · gmail_ingest_service                   → config de integraciones + pdf_gasto (Drive/media)
  · gmail_imap                             → leer un correo y mover etiquetas

Tres entradas:
  · procesar_mensaje(message_id)   → correo NUEVO del INBOX (clasifica → gasto / incidencia).
  · procesar_revisadas(...)        → correo en Facturas/Facturas revisadas: el usuario YA
                                      confirmó a mano que es factura real (lo movió desde
                                      Incidencias) → se registra SIEMPRE, nunca se descarta.
  · reprocesar_gasto(gid, bucket)  → fila YA existente del backlog (buckets A/B/C/E/F).

Flujo de carpetas (decisión del usuario, 2026-08-09):
  INBOX → (automático) → Facturas/Facturas Procesadas   [confianza alta, se registra solo]
                       → Facturas/Incidencias            [duda: no se registra nada aún]
  Facturas/Incidencias → (revisión humana en Gmail) → Facturas/Facturas revisadas [factura confirmada]
                                                      → se borra a mano            [no era factura]
  Facturas/Facturas revisadas → (automático) → se registra SIEMPRE + Facturas/Facturas Procesadas
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlmodel import Session, select

from application.services.extract_service import (IDS_ADMINISTRADORES, ExtractionError, extraer_desde_pdf,
                                                  extraer_desde_texto)
from application.services.gmail_ingest_service import GmailIngestService
from domain.models.config import Integracion
from domain.models.gestoria import Gasto, GastoIncidencia, Proveedor
from domain.services import clasificador_factura as clf
from domain.services import invoice_validator as v
from domain.services.invoice_extractor import normalize_proveedor, normalizar_cif
from domain.services.proveedor_resolver import resolver_proveedor
from infrastructure.external_apis import gmail_imap
from infrastructure.external_apis.portal_browser import leer_portal

# 22-oct-2026: corregidas contra el buzon real. El prefijo NO es "Facturas/" — ninguna
# carpeta con ese nombre existe (listadas las 16 del buzon via IMAP). Las reales cuelgan de
# "Gastos/" y estan numeradas. Con los valores anteriores _fetch_email_completo buscaba en
# 3 carpetas inexistentes + INBOX, asi que SIEMPRE devolvia "Email no encontrado" y el
# barrido de Gmail no proceso ni un correo: 827 esperando en "Gastos/1. Gastos sin procesar".
# CARPETA_ENTRADA es esa bandeja de trabajo, no INBOX: los correos llegan ya etiquetados.
ETIQUETA_INCIDENCIAS = "Gastos/5. Incidencias"
ETIQUETA_PROCESADAS = "Gastos/4. Gastos Procesados"    # archivo: la factura OK sale de la bandeja de trabajo
ETIQUETA_REVISADAS = "Gastos/3. Gastos revisados"      # el usuario confirma aqui a mano
CARPETA_ENTRADA = "Gastos/1. Gastos sin procesar"
CARPETA_PAPELERA = "[Gmail]/Papelera"     # confirmado contra el buzón real, 2026-08-09
CIF_CONSENUR = "B86208824"
# Incidencias que fallaron por la IA (cuota 429, modelo retirado 404, JSON roto, nada leído) y
# no por la factura: tras cambiar de modelo/relevo vale la pena volver a leerlas.
MOTIVOS_RECUPERABLES = ("429", "http404", "etapa2", "sin_datos")
MAX_RONDAS_CORRECCION = 4
# Recibo de un SaaS/proveedor extranjero (Stripe & co.): importe en divisa, sin NIF español.
RE_RECIBO_EXTRANJERO = re.compile(r"(\$\s?\d|\d\s?\$|\bUSD\b|\bUS\$|\breceipt\b|\bamount paid\b)", re.I)


def _texto_fuente_email(email: dict) -> str:
    """Texto fuente para `_total_en_texto` cuando la factura viene de un PDF (adjunto,
    enlace, portal): cuerpo del correo + texto ya extraído del PDF (`pdf_texto`, calculado
    por `gmail_imap._parse_message`, I1 de la revisión final de rama). `""` si no hay nada
    (p.ej. dict de email mínimo) — seguro: el chequeo de "total literal" se salta sin
    texto fuente, igual que antes de este fix."""
    return f"{email.get('cuerpo') or ''}\n{email.get('pdf_texto') or ''}".strip()


def _texto_fuente_pdf(pdf_bytes: bytes, email: Optional[dict] = None) -> str:
    """I1 (re-revisión, ronda 2): texto fuente REAL para `_total_en_texto` cuando se tienen
    los bytes del documento (adjunto, enlace descargado, PDF de portal) — NO solo el cuerpo
    del correo. Mi primer intento (ronda 1) usaba únicamente `_texto_fuente_email(email)`
    en estos caminos, que es solo "Su factura está disponible" o similar: el total real
    está en el PDF, no en ese cuerpo, así que facturas válidas se rechazaban por error
    (total_no_literal_en_texto) tras agotar las 4 rondas — regresión Alta señalada por el
    re-revisor.

    Usa `gmail_imap._pdf_text` (ya existe, no requiere tocar extract_service.py) para
    extraer el texto de la capa de texto del PDF. Si HAY texto real del PDF, se combina con
    el del correo (por si el total aparece ahí además de en el PDF).

    I1 (re-revisión ronda 3 — corrige un hueco real): si el PDF NO tiene capa de texto
    (escaneado, foto sin OCR — `_pdf_text` devuelve "" o solo espacios), esta función debe
    devolver "" DIRECTAMENTE, sin sustituir ese vacío por el cuerpo del correo. El cuerpo
    del correo ("Factura adjunta, gracias") NUNCA contiene el total real de una factura
    escaneada, así que usarlo como texto_fuente aplicaba el chequeo de "total literal"
    sobre un texto que estructuralmente no puede contenerlo — rechazando por error facturas
    legítimas de proveedores que escanean/fotografían (caso frecuente en proveedores
    pequeños). Vacío real = el chequeo de `_total_en_texto` se salta en `_validar_datos`
    (comportamiento seguro ya implementado), que es exactamente lo correcto aquí: sin texto
    fiable del documento, no hay nada contra lo que comprobar el total."""
    texto_pdf = ""
    if pdf_bytes:
        try:
            texto_pdf = (gmail_imap._pdf_text(pdf_bytes) or "").strip()
        except Exception:  # raiz: PDF ilegible/cifrado al extraer el texto para validar el total -> texto vacio y el chequeo se salta; no tumba la lectura  # noqa: BLE001
            texto_pdf = ""
    if not texto_pdf:
        return ""
    texto_email = _texto_fuente_email(email) if email else ""
    return f"{texto_email}\n{texto_pdf}".strip()


def _detectar_mime(b: bytes) -> str:
    """MIME real por los magic bytes (los ficheros de Drive llegan como PDF, PNG o JPG)."""
    if b[:4] == b"%PDF":
        return "application/pdf"
    if b[:4] == b"\x89PNG":
        return "image/png"
    if b[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "application/pdf"  # desconocido → el pipeline intenta texto nativo y, si no, render


class Clasificacion(str, Enum):
    FACTURA = "FACTURA"
    NO_FACTURA = "NO_FACTURA"
    PORTAL = "PORTAL"
    ERROR = "ERROR"


@dataclass
class Fuente:
    """Contenido sobre el que se trabaja + su procedencia (correo o Drive)."""
    bytes: bytes = b""
    mime: str = "application/pdf"
    origen: str = "drive"          # drive | adjunto | enlace | media
    gmail_message_id: Optional[str] = None
    gmail_uid: Optional[str] = None
    remitente: Optional[str] = None
    asunto: Optional[str] = None
    fecha: Optional[date] = None

    def __post_init__(self) -> None:
        # gastos.gmail_message_id y gasto_incidencias.gmail_message_id son VARCHAR(120) con
        # UNIQUE en gastos. Algunas plataformas de marketing (Freshmarketer, visto en
        # producción 2026-08-10) generan Message-ID de 180+ caracteres — sin truncar aquí,
        # ese INSERT revienta con StringDataRightTruncation y, al no hacerse rollback, deja
        # la sesión envenenada para TODO lo que se procese después en la misma tanda (así se
        # perdieron 171 correos de un tirón). Se trunca UNA vez, en el único sitio que
        # construye el dato, para que guardar y comparar usen siempre el mismo valor.
        if self.gmail_message_id and len(self.gmail_message_id) > 120:
            self.gmail_message_id = self.gmail_message_id[:120]


RE_ORGANISMO_AEAT = re.compile(r"agencia (estatal|tributaria)|\baeat\b|delegaci[oó]n especial|recaudaci[oó]n|hacienda", re.I)
CIF_AEAT = "Q2826000H"


def _importes_texto(texto: str) -> list[str]:
    """Importes con dos decimales que aparecen en el documento (para el aviso de corrección, V7)."""
    return sorted({m.group(0) for m in re.finditer(
        r"(?<![\d.,])\d{1,3}(?:\.\d{3})*,\d{2}(?!\d)|(?<![\d.,])\d+\.\d{2}(?!\d)", texto or "")})[:40]


def _total_por_cuadre(d: dict, texto: str) -> Optional[Decimal]:
    """Total = base × (1 + IVA) + suplido − IRPF, solo si la base Y ese total aparecen literalmente
    en el documento. Corrige la IA cuando el desglose está desordenado (Culligan: base 8,19, IVA
    1,72, total 9,91 → la IA daba 11,63 sumando el IVA dos veces). No inventa: ambos importes
    tienen que estar escritos en el documento."""
    try:
        base = Decimal(str(d.get("base_imponible")))
        pct = Decimal(str(d.get("iva_pct") or 0))
    except Exception:  # raiz: base_imponible/iva_pct no numericos en los datos de la IA -> sin correccion del total (None)  # noqa: BLE001
        return None
    if not base or not _total_en_texto(base, texto):
        return None
    extra = Decimal(str(d.get("suplido") or 0)) - Decimal(str(d.get("retencion") or 0))
    total = (base * (1 + pct / 100) + extra).quantize(Decimal("0.01"))
    return total if total > 0 and _total_en_texto(total, texto) else None


_RE_ASUNTO_FACTURA = re.compile(r"factur|fatura|invoice|recibo|receipt", re.I)


def _proteger_facturas_del_descarte(res: "Resolucion", email: dict) -> "Resolucion":
    """La IA puede decir «descartado» (no es gasto), pero un correo que se anuncia como factura
    no se tira: va a incidencia para revisarlo. En la prueba de 106 correos reales la IA
    descartó facturas de Kokuai, Acudent y Dentix que sí lo eran."""
    if res.ok or not _RE_ASUNTO_FACTURA.search(email.get("asunto") or ""):
        return res
    inc = [("factura_no_legible:ia_dice_no_gasto:" + i.split(":", 1)[1]) if str(i).startswith("descartado_ia:") else i
           for i in res.incidencias or []]
    return Resolucion(ok=False, datos=res.datos, incidencias=inc, error=getattr(res, "error", None))


_RE_SUBTOTAL_PAGINA = re.compile(r"SUMA\s+Y\s+SIGUE|SUMA\s+ANTERIOR|SUBTOTAL\s+P[AÁ]G", re.I)


def _total_es_subtotal(total: Decimal, texto: str) -> bool:
    """El total solo aparece en líneas de arrastre entre páginas ("SUMA Y SIGUE 977,44"):
    la IA cogió el subtotal de la página 1 de una factura de varias (Dentix, 27-oct-2026)."""
    lineas = [l for l in (texto or "").splitlines() if _total_en_texto(total, l)]
    return bool(lineas) and all(_RE_SUBTOTAL_PAGINA.search(l) for l in lineas)


def _total_es_base(total: Decimal, texto: str) -> Optional[Decimal]:
    """Si el total por rótulo del documento es exactamente `total` + un tipo de IVA español,
    la IA devolvió la BASE como total (Turset: 344,23 × 1,21 = 416,52). Devuelve el total
    del rótulo; None si no hay rótulo o no encaja así (un rótulo que lee la base no dispara)."""
    from domain.services import gestor_lectura_fiscal as fiscal
    try:
        rotulo = fiscal.total_por_rotulo(texto or "")
    except Exception:  # raiz: motor fiscal (lectura de rotulo) falla -> comprobacion extra omitida; nunca bloquea la lectura  # noqa: BLE001
        return None
    if not rotulo or not total:
        return None
    for tipo in (Decimal("0.21"), Decimal("0.10"), Decimal("0.04")):
        if abs(abs(total) * (1 + tipo) - abs(rotulo)) <= Decimal("0.02"):
            return abs(rotulo)
    return None


@dataclass
class Resolucion:
    """Resultado de leer + validar una factura."""
    ok: bool
    datos: dict = field(default_factory=dict)
    incidencias: list = field(default_factory=list)
    error: Optional[str] = None


def _total_en_texto(total: Decimal, texto: str) -> bool:
    """Comprueba que el importe `total` aparece literalmente en `texto`.

    Se busca el valor absoluto (un abono trae el total en negativo, pero el texto
    fuente del PDF/email nunca imprime el signo) en sus variantes de formato
    habituales: con coma decimal y separador de miles con punto (es-ES, "1.234,56"),
    con coma decimal sin separador de miles ("145,42") y con punto decimal ("145.42"
    o "1234.56"). No se parsean todos los números del texto: basta con construir las
    variantes del propio total y buscarlas como subcadena.

    I5 (revisión final de rama + regresión corregida en ronda 2): además de las
    anteriores, cubre formatos reales que daban falso negativo: sin decimales
    ("Total: 50 €" cuando el total es 50.00), "50,- EUR" (coma-guion, uso
    centroeuropeo), con espacio como separador de miles ("1 234,56 €"), con UN solo
    decimal ("145,4 €" / "145.4"), y con separador de miles anglosajón-coma +
    decimal-punto ("$1,234.56"). El prefijo/sufijo de moneda no importa: se busca el
    número como subcadena con límites de dígito (`in`/regex), nunca el símbolo.

    CADA variante lleva su límite de "ni dígito ni separador decimal pegado" en AMBOS
    extremos (no solo al principio): la variante en-US de miles ("1,234", ronda 1) se
    olvidaba de incluir la parte decimal de vuelta, así que para un total menor de 1000
    (sin separador de miles) equivalía solo a la parte entera SIN exigir que el total
    terminase ahí — "12.30" matcheaba dentro de "12%" o de "1234,56" (el "12" inicial),
    y "145.42" dentro de "145,99" o de "145 unidades" (el "145" sin más). Corregido:
    toda variante que tenga parte entera + decimal lleva el decimal COMPLETO, y el
    lookaround final exige que no siga ni un dígito NI una coma/punto que pudiera ser
    el inicio de más decimales.
    """
    importe = abs(total)
    # Dos decimales fijos, sin separador de miles: "1234.56" / "145.42"
    plano = f"{importe:.2f}"
    parte_entera, parte_decimal = plano.split(".")
    miles_punto = f"{int(parte_entera):,}".replace(",", ".")   # "1.234"
    miles_coma = f"{int(parte_entera):,}"                      # "1,234"
    miles_espacio = miles_coma.replace(",", " ")                # "1 234"

    variantes = {
        # Separador de miles con punto, decimal con coma: "1.234,56"
        f"{miles_punto},{parte_decimal}",
        # Sin separador de miles, decimal con coma: "1234,56"
        f"{parte_entera},{parte_decimal}",
        # Decimal con punto, sin separador de miles: "1234.56"
        plano,
        # Separador de miles con coma, decimal con punto (en-US/$): "1,234.56"
        f"{miles_coma}.{parte_decimal}",
        # Separador de miles con espacio, decimal con coma (fr/es variante): "1 234,56"
        f"{miles_espacio},{parte_decimal}",
    }
    # Sin decimales: "50" cuando el importe es exactamente 50.00 ("Total: 50 €"). Solo se
    # añade cuando NO hay céntimos — si los hubiera, "50" sin decimales sería un número
    # DISTINTO (50 ≠ 50.42), no una variante de formato del mismo importe.
    if parte_decimal == "00":
        variantes.add(parte_entera)          # "50"
        variantes.add(miles_punto)           # "1.234" sin decimales
        variantes.add(miles_coma)            # "1,234" sin decimales
        variantes.add(miles_espacio)         # "1 234" sin decimales
        # "50,- EUR" / "50,-": coma-guion en vez de decimales (uso centroeuropeo).
        variantes.add(f"{parte_entera},-")
    # Un solo decimal cuando el segundo es 0: "145,4" / "145.4" para 145.40. Igual que
    # arriba, solo tiene sentido cuando el total REAL solo tiene un decimal significativo.
    if parte_decimal.endswith("0") and parte_decimal != "00":
        un_decimal = parte_decimal[0]
        variantes.add(f"{parte_entera},{un_decimal}")
        variantes.add(f"{parte_entera}.{un_decimal}")

    # Lookaround en AMBOS extremos: ni un dígito pegado antes, ni un dígito O separador
    # decimal (coma/punto) pegado después. Sin el límite final, una variante SIN decimales
    # (p.ej. "12" de un total de 12.30) matchearía dentro de un número con más dígitos tras
    # un separador que no sea dígito (p.ej. "12%" donde "%" no es dígito, PERO también
    # dentro de "12,99" si no se exigiera que lo que sigue no sea tampoco una coma/punto
    # seguidos de más dígitos) — de ahí el `(?![\d.,]\d)` además de `(?!\d)`: no basta con
    # que el carácter inmediato no sea dígito, tampoco puede ser el separador decimal de
    # un número más largo.
    return any(
        # (?<!\d[.,]): tampoco puede ser la cola de un número con separador de miles
        # ("145,42" dentro de "1.145,42").
        re.search(rf"(?<!\d)(?<!\d[.,]){re.escape(variante)}(?!\d)(?![.,]\d)", texto)
        for variante in variantes
    )


class IntakeService:
    def __init__(self, session: Session, centro_id: int) -> None:
        self.session = session
        self.centro_id = centro_id
        self._ingest = GmailIngestService(session)
        self._dominios_conocidos: Optional[set[str]] = None   # caché por instancia (ver abajo)
        self._cache_cifs: Optional[dict[str, set]] = None      # ver _cifs_por_proveedor

    # ───────────────────────── config / apoyos ─────────────────────────
    def _remitentes_conocidos(self) -> set[str]:
        """Dominios de remitentes que YA mandaron correo a alguna etiqueta CREADA por el
        usuario (Clínica, Facturas/*, Gestoria, Laboratorios...) — sacados del remitente REAL
        de esos correos, no de un campo de la ficha de proveedor (a menudo vacío). Quedan
        FUERA el INBOX (mezcla de todo, no filtrado) y las carpetas propias de Gmail
        (Enviados, Destacados, Todos, Papelera, Spam...). Si el remitente ya aparece en
        cualquier etiqueta creada, NUNCA se manda a la papelera, aunque el asunto de un correo
        nuevo suyo tenga pinta de marketing — un proveedor real también manda ofertas de vez
        en cuando. Decisión del usuario, 2026-08-10. Solo cabecera
        (BODY.PEEK[HEADER.FIELDS (FROM)]), nunca el cuerpo. Se calcula UNA vez por instancia
        (una tanda de procesar_buzon puede mirar cientos de correos nuevos)."""
        if self._dominios_conocidos is not None:
            return self._dominios_conocidos
        dominios: set[str] = set()
        cfg = self._imap_cfg()
        if not cfg:
            self._dominios_conocidos = dominios
            return dominios
        try:
            cli = gmail_imap._connect(cfg)
            typ, boxes = cli.list()
            carpetas = []
            if typ == "OK":
                for b in boxes or []:
                    line = b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b)
                    if "\\Noselect" in line:   # carpetas contenedoras (p.ej. "[Gmail]") sin correos propios
                        continue
                    m = re.search(r'"([^"]+)"\s*$', line)
                    if not m:
                        continue
                    nombre = m.group(1)
                    # SOLO etiquetas CREADAS por el usuario (Clínica, Facturas/*, Gestoria...),
                    # no el INBOX (buzón general, mezcla de todo) ni las carpetas propias de
                    # Gmail (Enviados, Destacados, Todos, Papelera, Spam...) — estas últimas
                    # SIEMPRE empiezan por "[Gmail]/" o son literalmente "[Gmail]" (decisión del
                    # usuario, 2026-08-10: "los remitentes de los mails que contienen una
                    # etiqueta CREADA").
                    if nombre.upper() == "INBOX" or nombre == "[Gmail]" or nombre.startswith("[Gmail]/"):
                        continue
                    carpetas.append(nombre)
            for carpeta in carpetas:
                try:
                    dest = f'"{carpeta}"' if " " in carpeta else carpeta
                    typ, _sel = cli.select(dest, readonly=True)
                    if typ != "OK":
                        continue
                    typ, data = cli.search(None, "ALL")
                    if typ != "OK" or not data or not data[0]:
                        continue
                    for uid in data[0].split():
                        typ2, hdata = cli.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM)])")
                        if typ2 != "OK" or not hdata or not hdata[0]:
                            continue
                        raw = hdata[0][1]
                        txt = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
                        m = re.search(r"@([\w.\-]+)", txt)
                        if m:
                            dominios.add(m.group(1).lower().rstrip(">").strip())
                except Exception:  # raiz: carpeta IMAP que no se puede leer -> se salta esa carpeta y siguen las demas  # noqa: BLE001
                    continue
            cli.logout()
        except Exception:  # raiz: sin IMAP la lista blanca queda vacía (cierra, no abre)
            pass
        self._dominios_conocidos = dominios
        return dominios

    def _integ(self, tipo: str):
        return self._ingest._integ(self.centro_id, tipo)

    def _llm_cfg(self) -> Optional[dict]:
        return self._ingest._llm_cfg(self.centro_id)

    def _imap_cfg(self) -> Optional[dict]:
        ig = self._integ("email_imap")
        return ig.config if (ig and ig.config) else None

    def _dominio_clinica(self) -> str:
        ig = self._integ("email_imap")
        cfg = ig.config if (ig and ig.config) else {}
        return (cfg.get("dominio_clinica")
                or clf.DOMINIOS_CLINICA_POR_DEFECTO[0])

    def _receptores(self) -> list:
        """CIFs de la propia clínica (para no confundir el del receptor con el del emisor)."""
        try:
            from domain.models.core import RazonSocial
            return [rs.cif for rs in self.session.exec(select(RazonSocial).where(
                RazonSocial.centro_id == self.centro_id)).all() if getattr(rs, "cif", None)]
        except Exception:  # raiz: esquema variable: la consulta de RazonSocial falla -> lista de CIFs propios vacia (no critico para validar)  # noqa: BLE001
            return []

    def _get_gasto(self, gid: int) -> Optional[Gasto]:
        g = self.session.get(Gasto, gid)
        return g if (g and g.centro_id == self.centro_id) else None

    # ───────────────────────── clasificación ─────────────────────────
    def _clasificar_detalle(self, email: dict) -> tuple[Clasificacion, str]:
        try:
            clase, motivo = clf.clasificar_email(email, dominio_clinica=self._dominio_clinica())
            return Clasificacion(clase), motivo
        except Exception as e:  # raiz: el clasificador de correo revienta (reglas/datos) -> se clasifica como ERROR con motivo y la pasada continua  # noqa: BLE001
            return Clasificacion.ERROR, f"clasificacion:{e}"

    def clasificar(self, email: dict) -> Clasificacion:
        """Clase del correo: FACTURA | NO_FACTURA | PORTAL | ERROR."""
        return self._clasificar_detalle(email)[0]

    # ───────────────────────── lectura + validación ─────────────────────────
    def _validar_datos(self, datos: dict, texto_fuente: str = "") -> Resolucion:
        """Sanea + valida un dict extraído (de un PDF o del cuerpo de un correo) y decide si es una
        factura FIABLE (coherente + total>0 + CIF de un tercero). Punto único reutilizado.

        Si se pasa `texto_fuente` (el texto plano del PDF/email de origen), se comprueba además
        que el total extraído aparece LITERALMENTE en ese texto: un total "calculado" (sumando
        o redondeando conceptos) que no esté escrito tal cual en el documento es señal de que el
        modelo inventó o combinó mal los importes."""
        if datos.get("accion") == "descartado" and not float(datos.get("total") or 0):
            # V7: la IA dice que no sale dinero y no hay ningún importe → no es un gasto (propuestas,
            # consultas a la gestoría, avisos sin importe...). Con importe NUNCA se descarta.
            motivo = (datos.get("motivo_descarte") or "sin_importe")[:100]
            return Resolucion(ok=False, datos=dict(datos), incidencias=[f"descartado_ia:{motivo}"])
        corregido = False
        if texto_fuente and datos.get("total") and not _total_en_texto(Decimal(str(datos["total"])), texto_fuente):
            cuadrado = _total_por_cuadre({**datos, "retencion": datos.get("irpf")}, texto_fuente)
            if cuadrado is not None:
                datos, corregido = {**datos, "total": float(cuadrado)}, True
        d = {"proveedor": datos.get("proveedor"), "cif": datos.get("cif_emisor"),
             "numero_factura": datos.get("numero_factura"),
             "fecha_factura": date.fromisoformat(datos["fecha"]) if datos.get("fecha") else None,
             "base_imponible": datos.get("base_imponible"), "iva_pct": datos.get("iva_pct"),
             "suplido": datos.get("suplido"), "retencion": datos.get("irpf"), "total": datos.get("total")}
        # El IRPF leído no llegaba al validador: alquileres y colaboradores nunca cuadraban.
        saneado, incidencias = v.validar(d, date.today(), self._receptores() + sorted(IDS_ADMINISTRADORES))
        saneado["proveedor_extraido"] = datos.get("proveedor")
        from domain.services import gestor_lectura_fiscal as fiscal
        if datos.get("proveedor") and fiscal.es_denominacion_propia(datos["proveedor"]):
            # El CIF puede ser de un tercero, pero si el NOMBRE es la clínica la lectura está
            # cruzada (gasto 4987 del 27-oct-2026 quedó registrado a nombre de TRIDENTAL).
            incidencias.append("proveedor_es_clinica")
            saneado["proveedor"] = saneado["proveedor_extraido"] = None
        if corregido:
            saneado["total_corregido_por_cuadre"] = True
        # Registro completo de gestoría: el validador solo mira lo fiscal; estos campos
        # descriptivos pasan tal cual para que _volcar_datos los persista.
        for campo in ("direccion", "telefono", "email", "tipo_documento", "concepto",
                      "irpf", "seguridad_social", "categoria", "divisa", "cuota_iva"):
            if datos.get(campo) is not None:
                saneado[campo] = datos[campo]
        ok = (not incidencias and bool(saneado.get("total")) and float(saneado.get("total") or 0) > 0
              and bool(saneado.get("cif")))
        if (not ok and texto_fuente and not saneado.get("cif") and set(incidencias) <= {"cif_receptor"}
                and float(saneado.get("total") or 0) > 0):
            ok = self._rescatar_emisor(saneado, texto_fuente)
            if ok:
                incidencias = []
        if (ok and texto_fuente and saneado.get("total")
                and not _total_en_texto(Decimal(str(saneado["total"])), texto_fuente)):
            ok = False
            incidencias.append("total_no_literal_en_texto")
        if ok and texto_fuente:
            total = Decimal(str(saneado["total"]))
            if _total_es_subtotal(total, texto_fuente):
                ok = False
                incidencias.append("total_es_subtotal_de_pagina")
            else:
                real = _total_es_base(total, texto_fuente)
                if real is not None:
                    ok = False
                    incidencias.append(f"total_es_base:{real}")
        return Resolucion(ok=ok, datos=saneado, incidencias=incidencias)

    def _cifs_por_proveedor(self) -> dict[str, set]:
        """{nombre normalizado → CIFs ya registrados} a partir de proveedores y gastos previos."""
        if self._cache_cifs is None:
            idx: dict[str, set] = {}
            filas = [(p.nombre, p.cif) for p in self.session.exec(select(Proveedor).where(
                Proveedor.centro_id == self.centro_id, Proveedor.cif.is_not(None))).all()]
            filas += list(self.session.exec(select(Gasto.proveedor_extraido, Gasto.cif_emisor).where(
                Gasto.centro_id == self.centro_id, Gasto.cif_emisor.is_not(None))).all())
            for nombre, cif in filas:
                n, c = normalize_proveedor(nombre or ""), normalizar_cif(cif)
                if n and c:
                    idx.setdefault(n, set()).add(c)
            self._cache_cifs = idx
        return self._cache_cifs

    def _rescatar_emisor(self, saneado: dict, texto_fuente: str) -> bool:
        """Cuando lo ÚNICO que falla es el CIF (vacío o el de la clínica) se intenta identificar al
        emisor sin inventar nada. Prueba de 200 correos reales (27-oct-2026): la mitad de las
        facturas con total correcto caían solo por esto.

        · Proveedor ya conocido: si en BD su nombre tiene UN único CIF, se usa ese (IPD, Kokuai…).
        · Recibo extranjero (Stripe, SaaS de EEUU/Asia): no lleva NIF español; se acepta sin CIF
          si el documento no trae ningún identificador fiscal español y el importe va en divisa.
        La clínica nunca se rescata como proveedor. El total literal se sigue exigiendo después."""
        from domain.services import gestor_lectura_fiscal as fiscal
        nombre = saneado.get("proveedor") or saneado.get("proveedor_extraido")
        if not nombre or fiscal.es_denominacion_propia(nombre):
            return False
        propios = {normalizar_cif(c) for c in self._receptores()} | {"B88393764"} | set(IDS_ADMINISTRADORES)
        ids_es = [i for i in fiscal.identificadores(texto_fuente) if normalizar_cif(i) not in propios]
        if RE_ORGANISMO_AEAT.search(nombre) and not ids_es:   # V7: CIF_ORGANISMOS
            # Solo si el documento no trae el CIF de otro emisor: una factura de Servicopy quedó
            # registrada como AEAT (gasto 4985) porque la IA escribió ese nombre.
            saneado.update(cif=CIF_AEAT, proveedor="Agencia Tributaria", cif_origen="organismo_publico")
            return True
        cifs = self._cifs_por_proveedor().get(normalize_proveedor(nombre)) or set()
        cifs -= {normalizar_cif(c) for c in self._receptores()}
        if len(cifs) == 1:
            cif = cifs.pop()
            if ids_es and cif not in {normalizar_cif(i) for i in ids_es}:
                return False        # el documento trae el CIF de OTRO emisor: el nombre de la IA no cuadra
            saneado.update(cif=cif, proveedor=nombre, cif_origen="proveedor_conocido")
            return True
        if not cifs and not ids_es and RE_RECIBO_EXTRANJERO.search(texto_fuente):
            saneado.update(proveedor=nombre, cif_origen="extranjero_sin_id_fiscal")
            return True
        return False

    def _feedback_reintento(self, res: Resolucion, texto_fuente: str = "",
                            primera_ronda: bool = False) -> Optional[str]:
        """Construye el aviso para un reintento de lectura cuando la validación rechazó la
        extracción por errores tipicamente de LECTURA del modelo (CIF receptor/vacío, suplido
        no capturado, IVA incoherente, base>total). Si no aplica, devuelve None (=no reintentar).

        I4 (revisión final de rama): si en la PRIMERA ronda no hay NINGÚN total y NINGÚN CIF
        en absoluto (ambos completamente vacíos, no solo inválidos), no se reintenta — es la
        señal de "este documento no es una factura" (banner de cookies, landing sin factura),
        no de "dato parcialmente mal leído". Reintentar ahí solo agota las 4 rondas sin que
        haya nada que una ronda adicional pueda corregir."""
        datos = res.datos or {}
        if any(str(i).startswith("descartado_ia:") for i in res.incidencias or []):
            return None
        if primera_ronda and not datos.get("cif") and not datos.get("total"):
            return None
        incid_txt = "; ".join(res.incidencias or [])
        _low = incid_txt.lower()
        rein = ((not (res.datos or {}).get("cif"))
                or "cif" in _low or "receptor" in _low
                or "suplido" in _low or "iva_incoherente" in _low
                or "base_mayor_total" in _low
                or "total_no_literal_en_texto" in _low
                or "total_es_" in _low or "proveedor_es_clinica" in _low
                or (res.datos or {}).get("total") in (None, 0, "0", ""))
        if not rein or not incid_txt:
            return None
        fb = (f"El validador rechazó tu extracción por: {incid_txt[:170]}. "
              "Probablemente confundiste bloques o te saltaste un importe. Relee el documento completo.")
        if "cif" in _low or "receptor" in _low or not (res.datos or {}).get("cif"):
            fb += " Devuelve el CIF/NIF del EMISOR real (el proveedor que factura), normalmente junto a su razón social o en el pie."
        if "proveedor_es_clinica" in _low:
            fb += (" Pusiste a la CLÍNICA (Tridental / Rubio García) como proveedor: es el cliente. El "
                   "proveedor es la OTRA empresa del documento, la que emite y cobra.")
        if "suplido" in _low:
            fb += " Si la base+IVA no cuadra con el TOTAL, busca un importe 'suplido/a cuenta' e inclúyelo."
        if "iva_incoherente" in _low or "base_mayor_total" in _low:
            fb += " Comprueba que base_imponible, IVA y total sean coherentes entre sí."
        if "total_no_literal_en_texto" in _low:
            fb += (" El total que pusiste no aparece literalmente en el documento. Busca el importe "
                   "EXACTO que debe pagarse — no sumes conceptos ni lo redondees.")
            if texto_fuente:
                fb += f" Importes que SÍ aparecen en el documento: {_importes_texto(texto_fuente)}."
        if "total_es_subtotal_de_pagina" in _low:
            fb += (" El importe que diste es un 'SUMA Y SIGUE' / 'SUMA ANTERIOR' (subtotal entre páginas). "
                   "La factura tiene varias páginas: el TOTAL es el importe final de la última, junto al "
                   "cuadro de bases/IVA o a los vencimientos.")
        if "total_es_base:" in _low:
            real = _low.split("total_es_base:")[1].split(";")[0].strip()
            fb += (f" El importe que diste como total es la BASE imponible: el documento indica un total "
                   f"a pagar de {real}. Devuelve base, IVA y total coherentes con eso.")
        return fb

    def resolver_factura(self, fuente: Fuente, texto_fuente: str = "") -> Resolucion:
        """Lee la factura del ADJUNTO/PDF (pipeline 2-etapas) y la valida.
        Si la validación rechaza (CIF receptor/vacío, suplido no capturado, total inventado...),
        REINTENTA pasándole al modelo el feedback del validador, hasta MAX_RONDAS_CORRECCION
        veces: la mayoría de esos fallos son el modelo confundiendo bloques o importes, y con el
        aviso se corrige. Si tras agotar las rondas sigue sin validar, se devuelve la última
        Resolucion (incidencia) — nunca una excepción ni un bucle infinito."""
        llm = self._llm_cfg()
        if not llm:
            return Resolucion(ok=False, error="IA no configurada (integraciones.tipo='llm')")
        aviso = None
        res = Resolucion(ok=False, error="sin intentos")
        for ronda in range(MAX_RONDAS_CORRECCION):
            try:
                datos = extraer_desde_pdf(fuente.bytes, fuente.mime, llm, aviso=aviso)
            except ExtractionError as e:
                return res if res.datos else Resolucion(ok=False, error=str(e))
            res = self._validar_datos(datos, texto_fuente)
            if res.ok:
                return res
            aviso = self._feedback_reintento(res, texto_fuente, primera_ronda=(ronda == 0))
            if aviso is None:
                return res
        return res

    def _extraer_de_correo(self, texto: str, texto_fuente: str = "") -> Resolucion:
        """Extrae la factura del CUERPO de un correo (cuando viene en el email, no en un adjunto).
        El cuerpo del correo ES el texto fuente en este camino: si no se pasa uno explícito, se
        usa `texto` para la comprobación de "total literal en el documento"."""
        llm = self._llm_cfg()
        if not (llm and texto and texto.strip()):
            return Resolucion(ok=False, error="sin IA o sin texto")
        texto_fuente = texto_fuente or texto
        aviso = None
        res = Resolucion(ok=False, error="sin intentos")
        for ronda in range(MAX_RONDAS_CORRECCION):
            try:
                datos = extraer_desde_texto(texto, llm, aviso=aviso)
            except ExtractionError as e:
                return res if res.datos else Resolucion(ok=False, error=str(e))
            res = self._validar_datos(datos, texto_fuente)
            if res.ok:
                return res
            aviso = self._feedback_reintento(res, texto_fuente, primera_ronda=(ronda == 0))
            if aviso is None:
                return res
        return res

    def _leer_sin_adjunto(self, email: dict, fuente: Fuente) -> Resolucion:
        """Factura clasificada SIN adjunto legible: intenta leerla igualmente por tres vías, en orden:
          1) descargar el PDF del ENLACE del correo (avisos de portal con enlace directo),
          1b) si el enlace no es un documento reconocible, abrir el portal con un navegador real
              (Playwright, vía `leer_portal`) por si el PDF solo aparece tras ejecutar JS / login,
          2) extraer la factura del CUERPO del correo (facturas escritas en el propio mensaje).
        Marca `fuente.origen` con la vía que funcionó. Resolucion(ok=False) si ninguna cuadra."""
        # 1 · Enlaces de descarga del HTML (descargar_enlace lleva guarda anti-SSRF).
        # I3 (revisión final de rama): valores ORIGINALES de fuente, para restaurarlos en
        # cada `continue` donde se haya mutado `fuente` sin que ese intento validara — si
        # no se restaura, un PDF descartado (del portal o de un enlace) queda contaminando
        # fuente.bytes/mime/origen y, si luego gana otra vía (el cuerpo del correo), ese PDF
        # erróneo puede archivarse contra el gasto equivocado.
        bytes_orig, mime_orig, origen_orig = fuente.bytes, fuente.mime, fuente.origen
        for url in (email.get("enlaces") or [])[:3]:
            bajado = gmail_imap.descargar_enlace(url)
            contenido = bajado.get("content") if bajado else None
            # Solo si el enlace devuelve un DOCUMENTO (PDF/imagen); una página de login del portal
            # (HTML) se descarta y se pasa al siguiente enlace / al cuerpo.
            if not contenido or contenido[:5] != b"%PDF-" and contenido[:4] != b"\x89PNG" and contenido[:2] != b"\xff\xd8":
                # 1b · El enlace no trajo un documento directo: puede que el portal solo sirva el PDF
                # tras ejecutar JS (o requiera login). Se intenta con un navegador real antes de
                # pasar al siguiente enlace / al cuerpo del correo.
                portal = leer_portal(url)
                if portal.get("pdf_bytes"):
                    fuente.bytes = portal["pdf_bytes"]
                    fuente.mime = _detectar_mime(portal["pdf_bytes"])
                    fuente.origen = "portal"
                    # I1 (ronda 2): se usa el texto REAL del PDF descargado del portal
                    # (gmail_imap._pdf_text), no solo el cuerpo del correo — el total está
                    # en el documento, no en "Su factura está disponible".
                    res = self.resolver_factura(
                        fuente, texto_fuente=_texto_fuente_pdf(portal["pdf_bytes"], email))
                    if res.ok:
                        return res
                    fuente.bytes, fuente.mime, fuente.origen = bytes_orig, mime_orig, origen_orig
                    continue
                texto_portal = (portal.get("texto") or "").strip()
                if texto_portal and not portal.get("requiere_login") and not portal.get("error"):
                    res = self._extraer_de_correo(texto_portal)
                    if res.ok:
                        fuente.origen = "portal"
                        return res
                continue
            fuente.bytes = contenido
            fuente.mime = _detectar_mime(contenido)
            fuente.origen = "enlace"
            # I1 (ronda 2): texto REAL del PDF descargado del enlace, no solo el cuerpo.
            res = self.resolver_factura(fuente, texto_fuente=_texto_fuente_pdf(contenido, email))
            if res.ok:
                return res
            fuente.bytes, fuente.mime, fuente.origen = bytes_orig, mime_orig, origen_orig
        # 2 · La factura puede venir en el CUERPO del correo (texto, sin PDF).
        res = self._extraer_de_correo(email.get("cuerpo") or "")
        if res.ok:
            fuente.origen = "cuerpo"
        return res

    # ───────────────────────── escritura ─────────────────────────
    def _buscar_por_identidad(self, datos: dict) -> Optional[Gasto]:
        """Busca un gasto YA existente que sea la MISMA factura, para no duplicarla al llegar por
        otra fuente (subida de Drive, o el correo 'Pagada'/recordatorio de una factura ya registrada).

        1) Identidad fiscal fuerte: CIF emisor + nº de factura.
        2) Fallback SIN CIF fiable: nº de factura + total EXACTO. Los correos de recordatorio/'Pagada'
           reenvían la misma factura pero a menudo sin CIF legible; antes eso saltaba el dedup y
           duplicaba (nº + total exacto es identidad suficiente y evita el falso positivo de nº corto)."""
        numero = (datos.get("numero_factura") or "").strip()
        if not numero:
            return None
        cif = normalizar_cif(datos.get("cif"))
        if cif:
            g = self.session.exec(select(Gasto).where(
                Gasto.centro_id == self.centro_id,
                Gasto.cif_emisor == cif, Gasto.numero_factura == numero)).first()
            if g is not None:
                return g
        try:
            total = Decimal(str(datos.get("total")))
        except (TypeError, ValueError, ArithmeticError):
            return None
        if total <= 0:
            return None
        return self.session.exec(select(Gasto).where(
            Gasto.centro_id == self.centro_id,
            Gasto.numero_factura == numero, Gasto.total == total)).first()

    def registrar_gasto(self, datos: dict, fuente: Fuente) -> tuple[int, bool]:
        """Da de alta (o actualiza) un gasto a partir de datos validados.
        Devuelve (id, enlazado): enlazado=True si el correo se vinculó a un gasto YA existente
        (por identidad) en vez de crear uno nuevo."""
        g = None
        if fuente.gmail_message_id:
            g = self.session.exec(select(Gasto).where(
                Gasto.centro_id == self.centro_id,
                Gasto.gmail_message_id == fuente.gmail_message_id)).first()
        if g is None:
            # Aún no hay fila por este correo → ¿existe ya la MISMA factura por identidad fiscal?
            existente = self._buscar_por_identidad(datos)
            if existente is not None:
                # No duplicar: enlazar el correo a la factura que ya está (backfill del message_id).
                # Se rellena si la fila no tiene message_id REAL (vacío o placeholder 'upload:' de
                # una subida de Drive) → así el visor "ver correo" funciona y el buzón queda
                # idempotente (no se reprocesa ese correo en la próxima pasada). El PDF de Drive
                # sigue enlazado por archivo_pdf_url, que es un campo aparte.
                actual = existente.gmail_message_id or ""
                if fuente.gmail_message_id and (not actual or actual.startswith("upload:")):
                    existente.gmail_message_id = fuente.gmail_message_id
                    self.session.add(existente)
                    self.session.commit()
                self._cerrar_incidencias(fuente.gmail_message_id)
                return existente.id, True
            g = Gasto(centro_id=self.centro_id, fecha=fuente.fecha or date.today(),
                      gmail_message_id=fuente.gmail_message_id)
        self._aplicar_datos(g, datos)
        self.session.add(g)
        self.session.commit()
        self.session.refresh(g)
        self._cerrar_incidencias(fuente.gmail_message_id)
        return g.id, False

    def _cerrar_incidencias(self, gmail_message_id: Optional[str]) -> int:
        """El correo ya tiene gasto: sus incidencias anteriores dejan de tener sentido. Sin esto se
        quedaban huérfanas (244 de 322 en oct-2026) y engordaban la bandeja de incidencias."""
        if not gmail_message_id:
            return 0
        incs = self.session.exec(select(GastoIncidencia).where(
            GastoIncidencia.centro_id == self.centro_id,
            GastoIncidencia.gmail_message_id == gmail_message_id)).all()
        for inc in incs:
            self.session.delete(inc)
        if incs:
            self.session.commit()
        return len(incs)

    def _volcar_datos(self, g: Gasto, datos: dict) -> None:
        """Copia los campos extraídos+validados al gasto: los fiscales básicos Y el registro
        completo de gestoría (concepto, tipo, IRPF, categoría y snapshot del emisor con
        dirección/teléfono/email/S.S.)."""
        if datos.get("fecha_factura"):
            g.fecha = datos["fecha_factura"]
        g.proveedor_extraido = datos.get("proveedor_extraido") or g.proveedor_extraido
        g.cif_emisor = datos.get("cif") or g.cif_emisor
        g.numero_factura = datos.get("numero_factura") or g.numero_factura
        for campo in ("base_imponible", "iva_pct", "suplido", "total"):
            if datos.get(campo) is not None:
                setattr(g, campo, Decimal(str(datos[campo])))
        # ── Registro completo de gestoría ──
        if datos.get("concepto"):
            g.concepto = datos["concepto"]
        if datos.get("tipo_documento"):
            g.tipo_documento = datos["tipo_documento"][:20]
        if datos.get("irpf") is not None:
            g.retencion = Decimal(str(datos["irpf"]))   # IRPF en € (alquileres/doctores)
        if datos.get("categoria"):
            g.categoria = datos["categoria"][:40]
        if re.fullmatch(r"[A-Z]{3}", str(datos.get("divisa") or "")):
            g.divisa = datos["divisa"]       # antes nunca se guardaba: todo quedaba en EUR
        # Snapshot del emisor: dirección, teléfono, email (+ S.S. de nóminas como extra).
        emisor: dict = {}
        try:
            emisor = json.loads(g.emisor_datos) if g.emisor_datos else {}
        except Exception:  # raiz: emisor_datos corrupto o no-JSON en BD -> snapshot del emisor vacio; el gasto se guarda igual  # noqa: BLE001
            emisor = {}
        for k, v in (("direccion", datos.get("direccion")),
                     ("telefono", datos.get("telefono")),
                     ("email", datos.get("email"))):
            if v:
                emisor[k] = v
        if datos.get("seguridad_social") is not None:
            emisor["seguridad_social"] = float(datos["seguridad_social"])
        if emisor:
            emisor["fuente"] = "ia"
            g.emisor_datos = json.dumps(emisor, ensure_ascii=False)

    def _aplicar_datos(self, g: Gasto, datos: dict) -> None:
        """Factura FIABLE → vuelca datos, vincula proveedor por CIF y deja el gasto en 'pendiente'."""
        self._volcar_datos(g, datos)
        g.fiable = True
        g.incidencia = None
        g.incidencias = None
        # Solo se llega aquí con resolver_factura ok=True (cif + total>0 + sin incidencias) → el
        # veredicto del invariante único (gestoria_service._sincronizar_estado) sería 'pendiente'.
        g.estado = "pendiente"
        if g.cif_emisor:
            pid = resolver_proveedor(self.session, self.centro_id,
                                     g.proveedor_extraido, g.cif_emisor)
            if pid:
                g.proveedor_id = pid

    def _registrar_confirmada(self, res: Resolucion, email: dict, fuente: Fuente) -> int:
        """Correo en Facturas/Facturas revisadas: el usuario YA confirmó a mano que es una
        factura real (lo movió aquí desde Incidencias) — a diferencia del automático sobre el
        INBOX, esto NUNCA se descarta por duda. Si se pudo leer bien, sigue el camino normal
        (pendiente). Si no, se registra IGUAL en 'revisar' con lo que se haya podido extraer:
        el criterio de "es factura" ya lo puso una persona, lo único que falta es el dato."""
        if res.ok:
            gid, enlazado = self.registrar_gasto(res.datos, fuente)
            if not enlazado:
                self._archivar(gid, email, fuente)
            return gid
        g = None
        if fuente.gmail_message_id:
            g = self.session.exec(select(Gasto).where(
                Gasto.centro_id == self.centro_id,
                Gasto.gmail_message_id == fuente.gmail_message_id)).first()
        if g is None:
            g = Gasto(centro_id=self.centro_id, fecha=fuente.fecha or date.today(),
                      gmail_message_id=fuente.gmail_message_id)
        if res.datos:
            self._volcar_datos(g, res.datos)
        g.estado = "revisar"
        g.fiable = False
        g.incidencia = "confirmada_manual_falta_datos"
        self.session.add(g)
        self.session.commit()
        self.session.refresh(g)
        self._archivar(g.id, email, fuente)
        return g.id

    def registrar_incidencia(self, motivo: str, fuente: Fuente, *, commit: bool = True) -> int:
        """Apunta un correo que NO es gasto (ruido/portal/no-factura). Idempotente por message_id."""
        existe = None
        if fuente.gmail_message_id:
            existe = self.session.exec(select(GastoIncidencia).where(
                GastoIncidencia.centro_id == self.centro_id,
                GastoIncidencia.gmail_message_id == fuente.gmail_message_id)).first()
        if existe:
            existe.motivo = motivo[:200]
            self.session.add(existe)
            if commit:
                self.session.commit()
            return existe.id
        inc = GastoIncidencia(centro_id=self.centro_id, gmail_message_id=fuente.gmail_message_id,
                              fecha=fuente.fecha, remitente=(fuente.remitente or "")[:300] or None,
                              asunto=(fuente.asunto or "")[:400] or None, motivo=motivo[:200])
        self.session.add(inc)
        if commit:
            self.session.commit()
            self.session.refresh(inc)
        else:
            self.session.flush()
        return inc.id

    def mover_etiqueta(self, gmail_uid: str, etiqueta: str, *, origen: Optional[str] = None) -> bool:
        """Mueve el correo (por UID) a una etiqueta/carpeta de Gmail. False si no hay IMAP/UID.

        `origen` es la carpeta DE VERDAD donde está el correo AHORA (la que se está recorriendo
        en esta pasada) — si no se pasa, cae a la de la config guardada, que puede estar
        desfasada (bug real, 2026-08-10: la config seguía en 'Facturas' mientras se procesaba
        INBOX, así que CADA movimiento fallaba en silencio — 261 correos clasificados bien en
        BBDD sin mover un solo correo de verdad en Gmail). Los llamadores deben pasar `origen`
        explícito siempre que sepan en qué carpeta están.

        SEGURIDAD: mover correos en el buzón real es una acción externa difícil de revertir, así
        que está GUARDADA tras INTAKE_MOVER_GMAIL=1 (default OFF). Con el flag apagado se hace
        toda la reclasificación en BBDD (reversible) pero NO se toca Gmail. Para activarlo en el
        re-proceso operativo: `INTAKE_MOVER_GMAIL=1` en el entorno del proceso."""
        if os.environ.get("INTAKE_MOVER_GMAIL") != "1":
            return False
        cfg = self._imap_cfg()
        if not cfg or not gmail_uid:
            return False
        origen = origen or cfg.get("carpeta") or "INBOX"
        try:
            return gmail_imap.mover(cfg, origen, [str(gmail_uid)], etiqueta) > 0
        except Exception:  # raiz: mover/etiquetar en IMAP falla (caido/credenciales) -> False; el gasto ya registrado no se pierde  # noqa: BLE001
            return False

    # ───────────────────────── entradas públicas ─────────────────────────
    def _leer_factura_de_correo(self, email: dict, fuente: Fuente) -> Resolucion:
        """Lee la factura del adjunto; si no hay, del enlace de portal o del cuerpo del correo."""
        adj = (email.get("adjuntos") or [{}])[0]
        if adj.get("content"):
            fuente.bytes = adj["content"]
            fuente.mime = adj.get("content_type") or "application/pdf"
            fuente.origen = "adjunto"
            res = self.resolver_factura(fuente, texto_fuente=_texto_fuente_pdf(adj["content"], email))
        else:
            res = self._leer_sin_adjunto(email, fuente)
        return _proteger_facturas_del_descarte(res, email)

    def reintentar_incidencias(self, *, limite: Optional[int] = None, execute: bool = False,
                               throttle: float = 3.0) -> dict:
        """Vuelve a leer las incidencias que falló la IA (ver MOTIVOS_RECUPERABLES); el barrido
        normal nunca las reintenta porque su message_id ya está en BD.

        · Si el correo ya tiene gasto, la incidencia es huérfana: se cierra sin Gmail ni IA.
        · El correo se busca en Incidencias y, si no está, en Procesados (allí no se mueve).
        · execute=False: solo informa de cuántas se leerían ahora, sin escribir nada.
        · execute=True: las que se leen bien pasan a gasto (archivo + correo a Procesados) y se
          borra la incidencia; las demás se quedan como estaban, con el motivo actualizado."""
        import time
        cfg = self._imap_cfg()
        if not cfg:
            return {"ok": False, "error": "IMAP no configurado"}
        incs = [i for i in self.session.exec(select(GastoIncidencia).where(
                    GastoIncidencia.centro_id == self.centro_id).order_by(GastoIncidencia.created_at.desc())).all()
                if any(k in (i.motivo or "") for k in MOTIVOS_RECUPERABLES)]
        total = len(incs)
        if limite:
            incs = incs[:limite]
        res = {"ok": True, "execute": execute, "recuperables": total, "procesadas": len(incs),
               "recuperadas": 0, "enlazadas": 0, "yaConGasto": 0, "siguenMal": 0, "noFactura": 0,
               "noEncontradas": 0, "errores": 0, "detalle": []}
        for inc in incs:
            try:
                # Huérfana: el correo ya se registró como gasto por otra vía → solo hay que cerrarla.
                if self.session.exec(select(Gasto.id).where(
                        Gasto.centro_id == self.centro_id,
                        Gasto.gmail_message_id == inc.gmail_message_id)).first() is not None:
                    res["yaConGasto"] += 1
                    if execute:
                        self._cerrar_incidencias(inc.gmail_message_id)
                    continue
                email, carpeta = None, None
                for carpeta in (ETIQUETA_INCIDENCIAS, ETIQUETA_PROCESADAS):
                    email = gmail_imap.fetch_por_message_id(cfg, inc.gmail_message_id, carpeta=carpeta)
                    if email:
                        break
                if not email:
                    res["noEncontradas"] += 1
                    continue
                fuente = Fuente(gmail_message_id=inc.gmail_message_id, gmail_uid=email.get("uid"),
                                remitente=email.get("remitente"), asunto=email.get("asunto"),
                                fecha=email.get("fecha"))
                clase, _ = self._clasificar_detalle(email)
                if clase in (Clasificacion.NO_FACTURA, Clasificacion.ERROR):
                    res["noFactura"] += 1
                    continue
                lectura = self._leer_factura_de_correo(email, fuente)
                d = lectura.datos or {}
                fila = {"incidenciaId": inc.id, "asunto": (inc.asunto or "")[:80], "ok": lectura.ok,
                        "proveedor": d.get("proveedor_extraido"), "total": d.get("total")}
                if not lectura.ok:
                    res["siguenMal"] += 1
                    if execute:
                        inc.motivo = ("factura_no_legible:"
                                      + (lectura.error or ",".join(lectura.incidencias) or "sin_datos"))[:200]
                        self.session.add(inc)
                        self.session.commit()
                elif not execute:
                    res["recuperadas"] += 1
                else:
                    gid, enlazado = self.registrar_gasto(lectura.datos, fuente)
                    if not enlazado:
                        self._archivar(gid, email, fuente)
                    if carpeta != ETIQUETA_PROCESADAS:
                        self.mover_etiqueta(email.get("uid"), ETIQUETA_PROCESADAS, origen=carpeta)
                    res["enlazadas" if enlazado else "recuperadas"] += 1
                    fila["gastoId"] = gid
                res["detalle"].append(fila)
                time.sleep(throttle)
            except Exception as e:  # raiz: incidencia rota (datos/BD) -> rollback y se cuenta el error; no corta la pasada  # noqa: BLE001
                self.session.rollback()
                res["errores"] += 1
                res["detalle"].append({"incidenciaId": inc.id, "error": str(e)[:120]})
        return res

    def procesar_mensaje(self, gmail_message_id: str, *, carpeta: str = CARPETA_ENTRADA) -> dict:
        """Procesa un correo NUEVO del buzón: lo clasifica y lo convierte en gasto o incidencia.
        `carpeta` es la carpeta real donde vive ahora mismo (para mover_etiqueta) — por defecto
        INBOX, pero procesar_buzon la pasa explícita según la que esté recorriendo."""
        cfg = self._imap_cfg()
        if not cfg:
            return {"ok": False, "error": "IMAP no configurado"}
        email = gmail_imap.fetch_por_message_id(cfg, gmail_message_id)
        if not email:
            return {"ok": False, "error": "correo no encontrado"}
        fuente = Fuente(gmail_message_id=gmail_message_id, gmail_uid=email.get("uid"),
                        remitente=email.get("remitente"), asunto=email.get("asunto"),
                        fecha=email.get("fecha"))
        clase, motivo = self._clasificar_detalle(email)
        if clase == Clasificacion.NO_FACTURA:
            # Confiadamente NO es factura (ninguna señal de compra, sin adjunto) — el INBOX es
            # un buzón general, no todo lo que no es factura es una duda de facturación. Pero
            # "no es factura" NO es lo mismo que "es basura": dentro de esto hay correspondencia
            # real (RRHH, contratos, respuestas de trabajo) que nadie quiere perder. Solo lo que
            # es ruido automático INCONFUNDIBLE (alertas, códigos, bienvenidas) se tira solo; el
            # resto se deja tal cual en el INBOX (decisión del usuario, 2026-08-09: "si tengo
            # duda si es basura lo dejo en inbox; si es basura, a papelera").
            inc_id = self.registrar_incidencia(f"no_factura:{motivo}", fuente)
            dom = re.search(r"@([\w.\-]+)", email.get("remitente") or "")
            conocido = bool(dom and dom.group(1).lower().rstrip(">").strip() in self._remitentes_conocidos())
            if (not conocido) and clf.es_basura_confiable(email.get("asunto"), email.get("remitente")):
                self.mover_etiqueta(email.get("uid"), CARPETA_PAPELERA, origen=carpeta)
                return {"ok": True, "clase": clase.value, "motivo": motivo,
                        "incidenciaId": inc_id, "estado": "basura"}
            return {"ok": True, "clase": clase.value, "motivo": motivo,
                    "incidenciaId": inc_id, "estado": "descartado"}
        if clase == Clasificacion.ERROR:
            # Esto SÍ es un fallo real (ni se pudo clasificar el correo) — a Incidencias.
            inc_id = self.registrar_incidencia(f"error_clasificacion:{motivo}", fuente)
            self.mover_etiqueta(email.get("uid"), ETIQUETA_INCIDENCIAS, origen=carpeta)
            return {"ok": True, "clase": clase.value, "motivo": motivo,
                    "incidenciaId": inc_id, "estado": "incidencia"}
        res = self._leer_factura_de_correo(email, fuente)
        if res.ok:
            gid, enlazado = self.registrar_gasto(res.datos, fuente)
            if not enlazado:                       # gasto NUEVO → archivar PDF + anotar en el registro
                self._archivar(gid, email, fuente)
            # Factura ya tratada → sacarla de la bandeja de trabajo al archivo "Facturas Procesadas".
            self.mover_etiqueta(email.get("uid"), ETIQUETA_PROCESADAS, origen=carpeta)
            return {"ok": True, "clase": "FACTURA", "via": fuente.origen,
                    "estado": "enlazado" if enlazado else "pendiente", "gastoId": gid}
        # No se pudo leer. PORTAL sin documento descargable → incidencia 'falta_documento'
        # (hay que bajar la factura del portal a mano); FACTURA sin datos legibles → misma
        # bandeja de Incidencias, para que el usuario decida a mano si es factura o no (regla
        # del usuario, 2026-08-09: la duda NUNCA se queda flotando sin registro ni carpeta —
        # antes esta rama no movía el correo ni dejaba rastro, se perdía de vista en el INBOX).
        descarte = next((i for i in res.incidencias or [] if str(i).startswith("descartado_ia:")), None)
        if descarte and clase != Clasificacion.PORTAL:
            # Leído y no es un gasto: mismo trato que un NO_FACTURA (registro, sin mover el correo).
            inc_id = self.registrar_incidencia(f"no_factura:{descarte}"[:200], fuente)
            return {"ok": True, "clase": Clasificacion.NO_FACTURA.value, "motivo": descarte,
                    "incidenciaId": inc_id, "estado": "descartado"}
        if clase == Clasificacion.PORTAL:
            motivo_inc = f"falta_documento:{motivo}"
        else:
            motivo_inc = f"factura_no_legible:{(res.error or ','.join(res.incidencias) or 'sin_datos')[:150]}"
        inc_id = self.registrar_incidencia(motivo_inc, fuente)
        self.mover_etiqueta(email.get("uid"), ETIQUETA_INCIDENCIAS, origen=carpeta)
        return {"ok": True, "clase": clase.value if clase == Clasificacion.PORTAL else "FACTURA",
                "estado": "incidencia", "motivo": motivo_inc, "incidenciaId": inc_id}

    def procesar_archivo_subido(self, contenido: bytes, filename: str = "") -> dict:
        """Da de alta una factura desde un archivo SUBIDO a mano (foto/escaneo/PDF). Mismo pipeline
        que el buzón: lee con IA, dedup por identidad fiscal (no duplica → enlaza), archiva el PDF y
        deja el gasto en 'pendiente'. Si no se puede leer, NO se pierde: se crea en 'revisar' con el
        documento adjunto para teclearlo. `gmail_message_id='upload:<uuid>'` (placeholder, excluido
        del dedup del buzón). Devuelve el shape que espera la UI de subida."""
        import uuid
        if not contenido:
            return {"ok": False, "error": "Archivo vacío"}
        fuente = Fuente(bytes=contenido, mime=_detectar_mime(contenido), origen="media",
                        gmail_message_id=f"upload:{uuid.uuid4().hex}", fecha=date.today())
        email = {"asunto": filename, "cuerpo": "", "adjuntos": []}   # para el fallback de guardar_pdf
        # I1 (ronda 2): se extrae el texto real de `contenido` con _texto_fuente_pdf — si es
        # una imagen/escaneo sin capa de texto (no un PDF con texto real), _pdf_text
        # devuelve "" y el chequeo se salta solo, sin necesidad de un "" explícito.
        res = self.resolver_factura(fuente, texto_fuente=_texto_fuente_pdf(contenido))
        if res.ok:
            gid, enlazado = self.registrar_gasto(res.datos, fuente)
            if not enlazado:                       # gasto NUEVO → archivar el PDF (Drive o local)
                self._archivar(gid, email, fuente)
            g = self.session.get(Gasto, gid)
            return {"ok": True, "id": gid, "duplicado": enlazado,
                    "estado": g.estado if g else "pendiente",
                    "proveedor": g.proveedor_extraido if g else None,
                    "total": float(g.total) if g and g.total else 0.0}
        # No legible (o IA no disponible): crear el gasto en 'revisar' CON el documento adjunto, para
        # que aparezca en el filtro "por revisar" y se teclee a mano en el visor. No se pierde la subida.
        g = Gasto(centro_id=self.centro_id, fecha=date.today(), gmail_message_id=fuente.gmail_message_id,
                  estado="revisar", fiable=False, incidencia="requiere_revision_manual")
        self.session.add(g); self.session.commit(); self.session.refresh(g)
        self._archivar(g.id, email, fuente)
        return {"ok": True, "id": g.id, "duplicado": False, "estado": "revisar",
                "proveedor": None, "total": 0.0, "error": res.error}

    def _msgids_en_bd(self) -> set[str]:
        """Message-ids YA registrados (gastos + incidencias) → los correos ya procesados."""
        def _n(v):
            return (v or "").strip().strip("<>").strip()
        g = {_n(v) for v in self.session.exec(select(Gasto.gmail_message_id).where(
            Gasto.centro_id == self.centro_id)).all() if v and not str(v).startswith("upload:")}
        i = {_n(v) for v in self.session.exec(select(GastoIncidencia.gmail_message_id).where(
            GastoIncidencia.centro_id == self.centro_id)).all() if v}
        return g | i

    def _msgids_gastos(self) -> set[str]:
        """Message-ids que YA son un GASTO real — a propósito NO incluye las incidencias.
        La usa procesar_revisadas: mover un correo a Facturas revisadas debe poder REVERTIR
        un 'no_factura' anterior, así que haber tenido una incidencia no puede bloquear el
        registro (si usara _msgids_en_bd, todo lo que ya se marcó no_factura quedaría
        atrapado ahí para siempre, aunque el usuario confirme a mano que sí es factura)."""
        def _n(v):
            return (v or "").strip().strip("<>").strip()
        return {_n(v) for v in self.session.exec(select(Gasto.gmail_message_id).where(
            Gasto.centro_id == self.centro_id)).all() if v and not str(v).startswith("upload:")}

    def archivar_bandeja(self, carpeta: str = CARPETA_ENTRADA) -> dict:
        """Vacía la bandeja de trabajo: mueve a su archivo los correos YA procesados (registrados en
        BD) — factura → 'Facturas Procesadas', no-factura → 'Facturas/Incidencias' — dejando en la
        bandeja SOLO lo pendiente. Idempotente. Toca el buzón real → guardado tras INTAKE_MOVER_GMAIL=1."""
        if os.environ.get("INTAKE_MOVER_GMAIL") != "1":
            return {"ok": False, "error": "mover en Gmail desactivado (INTAKE_MOVER_GMAIL=1 para activar)"}
        cfg = self._imap_cfg()
        if not cfg:
            return {"ok": False, "error": "IMAP no configurado"}
        def _n(v):
            return (v or "").strip().strip("<>").strip()
        gastos = {_n(v) for v in self.session.exec(select(Gasto.gmail_message_id).where(
            Gasto.centro_id == self.centro_id)).all() if v and not str(v).startswith("upload:")}
        incid = {_n(v) for v in self.session.exec(select(GastoIncidencia.gmail_message_id).where(
            GastoIncidencia.centro_id == self.centro_id)).all() if v}
        try:
            correos = gmail_imap.listar_carpeta_msgids(cfg, carpeta)
        except Exception as e:  # raiz: IMAP no lista la carpeta (caido/credenciales) -> {ok:False, error:imap:...}; el caller informa  # noqa: BLE001
            return {"ok": False, "error": f"imap: {str(e)[:80]}"}
        a_proc = [c["uid"] for c in correos if c.get("uid") and _n(c.get("msg_id")) in gastos]
        a_inc = [c["uid"] for c in correos if c.get("uid") and _n(c.get("msg_id")) in incid
                 and _n(c.get("msg_id")) not in gastos]
        movidos_p = gmail_imap.mover(cfg, carpeta, a_proc, ETIQUETA_PROCESADAS) if a_proc else 0
        movidos_i = gmail_imap.mover(cfg, carpeta, a_inc, ETIQUETA_INCIDENCIAS) if a_inc else 0
        return {"ok": True, "carpeta": carpeta, "enCarpeta": len(correos),
                "aProcesadas": movidos_p, "aIncidencias": movidos_i,
                "quedanPendientes": len(correos) - movidos_p - movidos_i}

    def razonar_ia(self, email: dict, fuente: Fuente) -> dict:
        """EL MODELO DE IA razona el correo completo (texto + páginas del adjunto como imagen)
        y DECIDE: gasto | incidencia | descartado. Sin reglas previas — devuelve su decisión
        y su motivo. Para 'gasto' incluye los datos extraídos ya en el shape que espera
        registrar_gasto (fecha_factura/proveedor_extraido/cif/numero/base_imponible/iva_pct/suplido/total).
        """
        import json as _json

        import httpx

        ig = self.session.exec(select(Integracion).where(
            Integracion.centro_id == self.centro_id,
            Integracion.tipo == "llm", Integracion.agente == "gestor_multimodal",
            Integracion.activo == True)).first()  # noqa: E712
        cfg = (ig.config if ig else {}) or {}
        key = cfg.get("api_key") or cfg.get("openrouter_api_key")
        # El modelo y la dirección salen de la configuración del centro: el que había aquí
        # escrito a mano (nemotron-nano-vl) fue RETIRADO de OpenRouter y daba 404.
        from domain.config.ia_multimodal import DEFAULT_CONFIG
        modelo = cfg.get("modelo") or DEFAULT_CONFIG.modelo
        base_url = (cfg.get("base_url") or DEFAULT_CONFIG.base_url).rstrip("/")
        timeout_s = int(cfg.get("timeout_segundos") or 240)
        if not key:
            return {"accion": "incidencia", "motivo": "ia:sin_clave_multimodal", "datos": {}}

        from domain.prompts.gasto_multimodal import SYSTEM_PROMPT

        contenido = [{"type": "text", "text":
                      f"REMITENTE: {email.get('remitente') or ''}\n"
                      f"ASUNTO: {email.get('asunto') or ''}\n\n"
                      f"CUERPO DEL CORREO:\n{(email.get('cuerpo') or '')[:4000]}"}]
        adj = (email.get("adjuntos") or [{}])[0]
        if adj.get("content"):
            from application.services.gmail_ingest_service import _pdf_a_imagenes
            for b64 in _pdf_a_imagenes(adj["content"], max_paginas=2, dpi=120):
                contenido.append({"type": "image_url",
                                  "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
            contenido.append({"type": "text", "text":
                              "(Las imágenes de arriba son el documento adjunto.)"})
        contenido.append({"type": "text", "text":
                          'Analiza TODO (correo + documento) y responde SOLO con JSON:\n'
                          '{"accion": "gasto" | "incidencia" | "descartado",\n'
                          ' "motivo": "razonamiento breve de tu decisión",\n'
                          ' "datos": {"fecha_factura": "YYYY-MM-DD", "proveedor_extraido": "", '
                          '"cif": "", "direccion": "", "telefono": "", "email": "", '
                          '"tipo_documento": "factura|abono|rectificativa|nomina|impuesto|otro", '
                          '"numero_factura": "", "concepto": "", "base_imponible": 0, '
                          '"iva_pct": 0, "suplido": 0, "irpf": 0, "seguridad_social": 0, '
                          '"categoria": "", "total": 0}}\n'
                          'El campo "datos" SOLO si accion="gasto". IRPF: capturar la retención '
                          'en € en alquileres y facturas de doctores/colaboradores. S.S.: solo '
                          'en nóminas. Si un dato no aparece en el documento, cadena vacía o 0.'})

        body = {**(cfg.get("extra_body") or {}),
                "model": modelo,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": contenido}],
                "temperature": 0.0, "max_tokens": 2500}
        try:
            r = httpx.post(base_url + "/chat/completions",
                           headers={"Authorization": f"Bearer {key}",
                                    "Content-Type": "application/json"},
                           json=body, timeout=timeout_s)
        except Exception as e:  # raiz: fallo de red al llamar a la IA -> devuelve incidencia ia_red, no rompe la pasada  # noqa: BLE001
            return {"accion": "incidencia", "motivo": f"ia_red:{str(e)[:100]}", "datos": {}}
        if r.status_code != 200:
            return {"accion": "incidencia",
                    "motivo": f"ia_http{r.status_code}:{r.text[:100]}", "datos": {}}
        content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        i, j = content.find("{"), content.rfind("}")
        if i == -1 or j <= i:
            return {"accion": "incidencia",
                    "motivo": f"ia_sin_json:{content[:90]}", "datos": {}}
        try:
            out = _json.loads(content[i:j + 1])
        except Exception as e:  # raiz: JSON de la IA invalido -> devuelve incidencia ia_json_invalido, no rompe la pasada  # noqa: BLE001
            return {"accion": "incidencia", "motivo": f"ia_json_invalido:{e}", "datos": {}}
        return {"accion": (out.get("accion") or "incidencia"),
                "motivo": (out.get("motivo") or "")[:180],
                "datos": (out.get("datos") or {})}

    def procesar_buzon(self, carpeta: str, *, limite: Optional[int] = None,
                       execute: bool = False, throttle: float = 3.0) -> dict:
        """Recorre una carpeta IMAP y procesa los correos NUEVOS (no vistos antes).

        Idempotente y seguro por diseño: salta los ya registrados (por message_id) y, al dar de
        alta, dedup-a por identidad fiscal (no duplica facturas ya existentes → las enlaza).

        · execute=False (por defecto, R5): PREVISUALIZA. Solo clasifica (heurístico, sin IA ni
          escrituras) y devuelve el reparto factura/no-factura de lo nuevo.
        · execute=True: procesa de verdad, FILA A FILA, con `throttle` s entre facturas (la IA de
          NVIDIA da 429 en ráfaga). Cada factura: alta nueva | enlace a existente | revisar.
        """
        import time
        cfg = self._imap_cfg()
        if not cfg:
            return {"ok": False, "error": "IMAP no configurado"}
        try:
            correos = gmail_imap.listar_carpeta_msgids(cfg, carpeta)
        except Exception as e:  # raiz: IMAP no lista la carpeta (caido/credenciales) -> {ok:False}; el caller informa  # noqa: BLE001
            return {"ok": False, "error": f"imap: {str(e)[:80]}"}
        en_bd = self._msgids_en_bd()
        def _n(v):
            return (v or "").strip().strip("<>").strip()
        nuevos = [c for c in correos if c.get("msg_id") and _n(c["msg_id"]) not in en_bd]
        total_nuevos = len(nuevos)
        if limite:
            nuevos = nuevos[:limite]
        res = {"ok": True, "carpeta": carpeta, "execute": execute,
               "enCarpeta": len(correos), "yaEnBd": len(correos) - total_nuevos,
               "nuevos": total_nuevos, "procesados": len(nuevos),
               "facturasNuevas": 0, "facturasEnlazadas": 0, "aRevisar": 0,
               # "descartadas" = no es factura pero TAMPOCO basura confiable (RRHH, respuestas
               # reales...): se deja tal cual en el INBOX, sin tocar. "basura" = ruido automático
               # inconfundible (alertas, códigos, bienvenidas): se manda sola a la papelera.
               # "incidencias" = duda real de FACTURA (portal conocido, o parecía factura y no
               # se pudo leer): estas SÍ están en Facturas/Incidencias esperando que las mires.
               "descartadas": 0, "basura": 0, "incidencias": 0, "errores": 0, "detalle": []}
        for c in nuevos:
            mid = c["msg_id"]
            if not execute:
                # PREVIEW barato: clasificar sin bajar/leer con IA ni escribir.
                email = gmail_imap.fetch_por_message_id(cfg, mid)
                clase = self.clasificar(email).value if email else "ERROR"
                res["detalle"].append({"msgId": mid, "clase": clase, "asunto": (email or {}).get("asunto")})
                if clase == "FACTURA":
                    res["facturasNuevas"] += 1
                elif clase == "NO_FACTURA":
                    dom = re.search(r"@([\w.\-]+)", (email or {}).get("remitente") or "")
                    conocido = bool(dom and dom.group(1).lower().rstrip(">").strip() in self._remitentes_conocidos())
                    if (not conocido) and email and clf.es_basura_confiable(email.get("asunto"), email.get("remitente")):
                        res["basura"] += 1
                    else:
                        res["descartadas"] += 1
                else:   # PORTAL o ERROR: duda real
                    res["incidencias"] += 1
                continue
            try:
                # Diseño híbrido: el pipeline OCR+estructura (calidad probada) lee las facturas;
                # los DESCARTES ya no los decide ninguna regla — los razona EL MODELO DE IA.
                email = gmail_imap.fetch_por_message_id(cfg, mid)
                if not email:
                    raise RuntimeError("correo no encontrado en IMAP")
                fuente = Fuente(gmail_message_id=mid, gmail_uid=email.get("uid"),
                                remitente=email.get("remitente"),
                                asunto=email.get("asunto"), fecha=email.get("fecha"))
                clase, motivo_clf = self._clasificar_detalle(email)
                if clase == Clasificacion.NO_FACTURA:
                    # Antes una regla lo descartaba sin más. Ahora LO RAZONA LA IA: si ella
                    # ve un gasto real donde la regla no lo vio, se registra igual.
                    dec = self.razonar_ia(email, fuente)
                    if dec.get("accion") == "gasto" and dec.get("datos"):
                        gasto_id, enlazado = self.registrar_gasto(dec["datos"], fuente)
                        res["facturasNuevas" if not enlazado else "facturasEnlazadas"] += 1
                        res["detalle"].append({"msgId": mid, "caja": "gasto_ia",
                                               "motivo": dec.get("motivo", "")[:150],
                                               "gastoId": gasto_id})
                        time.sleep(throttle)
                        continue
                    motivo_ia = dec.get("motivo") or motivo_clf
                    self.registrar_incidencia(f"ia_descarte:{motivo_ia[:120]}", fuente)
                    res["descartadas"] += 1
                    res["detalle"].append({"msgId": mid, "caja": "descartado_ia",
                                           "motivo": motivo_ia[:150]})
                    time.sleep(throttle)
                    continue
                # FACTURA o PORTAL → pipeline completo de lectura (OCR + estructura + validación)
                r = self.procesar_mensaje(mid, carpeta=carpeta)
            except Exception as e:  # raiz: fallo al procesar un correo (IA/BD) -> rollback por correo y continua; evita la cascada que perdio 171 correos  # noqa: BLE001
                # SIN esto, un fallo de BD deja la sesión envenenada y CADA correo
                # siguiente falla en cascada (así se perdieron 171 correos el 2026-08-10).
                self.session.rollback()
                res["errores"] += 1
                res["detalle"].append({"msgId": mid, "error": str(e)[:100]})
                continue
            estado = r.get("estado")
            if r.get("clase") == "FACTURA" and estado == "pendiente":
                res["facturasNuevas"] += 1
            elif estado == "enlazado":
                res["facturasEnlazadas"] += 1
            elif estado == "revisar":
                res["aRevisar"] += 1
            elif estado == "descartado":
                res["descartadas"] += 1
            elif estado == "basura":
                res["basura"] += 1
            else:
                res["incidencias"] += 1
            res["detalle"].append({"msgId": mid, "clase": r.get("clase"), "estado": estado,
                                   "gastoId": r.get("gastoId")})
            time.sleep(throttle)
        return res

    def procesar_revisadas(self, carpeta: str = ETIQUETA_REVISADAS, *, limite: Optional[int] = None,
                           execute: bool = False, throttle: float = 3.0) -> dict:
        """Recorre Facturas/Facturas revisadas: correos que el usuario YA confirmó a mano como
        factura real (los movió aquí desde Incidencias tras revisarlos en Gmail). A diferencia
        de `procesar_buzon` (que descarta lo dudoso a Incidencias), aquí NUNCA se descarta nada
        — el criterio de "es factura" ya lo puso una persona. Si no se puede leer el importe,
        se registra igual en 'revisar' para teclearlo a mano. Tras registrarse, el correo se
        archiva en Facturas Procesadas (ya está tratado, no se vuelve a mirar).

        Misma forma que procesar_buzon: execute=False previsualiza sin IA ni escrituras."""
        import time
        cfg = self._imap_cfg()
        if not cfg:
            return {"ok": False, "error": "IMAP no configurado"}
        try:
            correos = gmail_imap.listar_carpeta_msgids(cfg, carpeta)
        except Exception as e:  # raiz: IMAP no lista la carpeta (caido/credenciales) -> {ok:False}; el caller informa  # noqa: BLE001
            return {"ok": False, "error": f"imap: {str(e)[:80]}"}
        # OJO: dedup solo por GASTOS (no _msgids_en_bd), a propósito — un correo puede llegar
        # aquí precisamente para REVERTIR una incidencia previa (ver _msgids_gastos).
        en_bd = self._msgids_gastos()
        def _n(v):
            return (v or "").strip().strip("<>").strip()
        nuevos = [c for c in correos if c.get("msg_id") and _n(c["msg_id"]) not in en_bd]
        total_nuevos = len(nuevos)
        if limite:
            nuevos = nuevos[:limite]
        res = {"ok": True, "carpeta": carpeta, "execute": execute,
               "enCarpeta": len(correos), "yaEnBd": len(correos) - total_nuevos,
               "nuevos": total_nuevos, "procesados": len(nuevos),
               "registradas": 0, "conDatos": 0, "faltanDatos": 0, "errores": 0, "detalle": []}
        if not execute:
            res["detalle"] = [{"msgId": c["msg_id"], "asunto": None} for c in nuevos]
            return res
        for c in nuevos:
            mid = c["msg_id"]
            try:
                email = gmail_imap.fetch_por_message_id(cfg, mid)
                if not email:
                    res["errores"] += 1
                    res["detalle"].append({"msgId": mid, "error": "correo no encontrado"})
                    continue
                fuente = Fuente(gmail_message_id=mid, gmail_uid=email.get("uid"),
                                remitente=email.get("remitente"), asunto=email.get("asunto"),
                                fecha=email.get("fecha"))
                adj = (email.get("adjuntos") or [{}])[0]
                if adj.get("content"):
                    fuente.bytes = adj["content"]
                    fuente.mime = adj.get("content_type") or "application/pdf"
                    fuente.origen = "adjunto"
                    # I1 (ronda 2): texto REAL del adjunto, no solo el cuerpo.
                    resl = self.resolver_factura(fuente, texto_fuente=_texto_fuente_pdf(adj["content"], email))
                else:
                    resl = self._leer_sin_adjunto(email, fuente)
                gid = self._registrar_confirmada(resl, email, fuente)
                self.mover_etiqueta(email.get("uid"), ETIQUETA_PROCESADAS, origen=carpeta)
                res["registradas"] += 1
                res["conDatos" if resl.ok else "faltanDatos"] += 1
                res["detalle"].append({"msgId": mid, "gastoId": gid, "fiable": resl.ok})
            except Exception as e:  # raiz: fallo procesando un correo -> rollback y sigue con el resto; un correo no tumba la pasada  # noqa: BLE001
                self.session.rollback()   # sin esto, un fallo aquí encadena todos los siguientes
                res["errores"] += 1
                res["detalle"].append({"msgId": mid, "error": str(e)[:100]})
                continue
            if throttle:
                time.sleep(throttle)   # misma cautela anti-429 que procesar_buzon
        return res

    def reprocesar_gasto(self, gid: int, bucket: str, *, motivo: Optional[str] = None,
                         commit: bool = True) -> dict:
        """Reprocesa UNA fila existente del backlog según su bucket. Devuelve el detalle del cambio.
        commit=False deja la transacción abierta (el script de backlog controla el commit, R5)."""
        g = self._get_gasto(gid)
        if not g:
            return {"ok": False, "error": "gasto no encontrado", "id": gid}
        antes = g.estado
        bucket = (bucket or "").upper()
        if bucket == "A":
            out = self._bucket_a(g)
        elif bucket == "B":
            out = self._bucket_b(g)
        elif bucket == "C":
            out = self._bucket_c(g)
        elif bucket == "E":
            out = self._bucket_e(g)
        elif bucket == "F":
            out = self._marcar_no_factura(g, motivo or "no_factura:revision_manual")
        elif bucket == "D":
            out = {"ok": False, "detalle": "Bucket D (IVA mixto IPD) fuera de alcance: ids ya 'pagada'. "
                                           "Requiere migración 017 (ivas JSONB) dedicada."}
        else:
            return {"ok": False, "error": f"bucket desconocido: {bucket}", "id": gid}
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return {"ok": out.get("ok", True), "id": gid, "estadoAnterior": antes,
                "estadoNuevo": g.estado, "detalle": out.get("detalle", "")}

    def _archivar(self, gid: int, email: dict, fuente: Fuente) -> None:
        """Guarda el PDF de la factura (Drive o local). Los datos ya están en la web/BD, no se
        duplican en ninguna hoja. Nunca rompe el alta: si algo falla, se ignora el archivado."""
        try:
            from application.services import factura_archivo as fa
            g = self.session.get(Gasto, gid)
            if not g:
                return
            fa.guardar_pdf(self.session, self.centro_id, g, email, fuente)
            self.session.commit()
        except Exception:  # raiz: archivar el PDF de la factura falla (disco/BD) -> rollback; el gasto no se pierde  # noqa: BLE001
            self.session.rollback()

    # ── lógica por bucket (re-proceso de filas existentes) ──
    def _bucket_a(self, g: Gasto) -> dict:
        """Drive + datos vacíos → leer el PDF con el pipeline y, si cuadra, pasar a 'pendiente'."""
        pdf = self._ingest.pdf_gasto(self.centro_id, g.id)
        if not pdf:
            g.incidencia = "requiere_revision_manual"
            return {"ok": False, "detalle": "sin PDF descargable de Drive"}
        # I1 (ronda 2): sí hay bytes del PDF aquí (descargado de Drive) — se extrae su texto
        # real con _texto_fuente_pdf en vez de saltarse el chequeo con "". No hay email
        # dict en este camino (reproceso de una fila ya existente, no de un correo), de ahí
        # el segundo argumento None.
        res = self.resolver_factura(Fuente(bytes=pdf, mime=_detectar_mime(pdf), origen="drive"),
                                    texto_fuente=_texto_fuente_pdf(pdf))
        if res.ok:
            self._aplicar_datos(g, res.datos)
            self.session.add(g)
            return {"ok": True, "detalle": f"extraído → pendiente (cif {g.cif_emisor})"}
        g.incidencia = "requiere_revision_manual"
        g.fiable = False
        self.session.add(g)
        return {"ok": False, "detalle": f"no validado: {res.error or ','.join(res.incidencias)}"}

    def _bucket_b(self, g: Gasto) -> dict:
        """Aviso de portal sin adjunto → incidencia 'falta_documento_portal:<portal>' + no_factura."""
        portal = clf._portal_de((g.proveedor_extraido or "").lower()) or "portal"
        return self._marcar_no_factura(g, f"falta_documento_portal:{portal}")

    def _bucket_c(self, g: Gasto) -> dict:
        """Abre el correo real y: (1) EXTRAE la factura de su cuerpo → si está completa, 'pendiente';
        (2) si trae importe pero falta el CIF, rellena y deja en 'revisar'; (3) si no hay factura
        legible, clasifica el sobre (no_factura / portal / se queda)."""
        cfg = self._imap_cfg()
        if not cfg or not g.gmail_message_id or g.gmail_message_id.startswith("upload:"):
            return {"ok": False, "detalle": "sin correo IMAP asociado"}
        try:
            email = gmail_imap.fetch_por_message_id(cfg, g.gmail_message_id)
        except Exception as e:  # raiz: IMAP caido/credenciales -> el gasto se queda en 'revisar' y se informa del error  # noqa: BLE001
            return {"ok": False, "detalle": f"imap_error: {str(e)[:60]}"}
        if not email:
            return {"ok": False, "detalle": "correo no encontrado en el buzón"}
        # 1 · La factura puede venir EN EL CUERPO del correo → extraerla y, si cuadra, darla de alta.
        res = self._extraer_de_correo(email.get("cuerpo") or "")
        if res.ok:
            self._aplicar_datos(g, res.datos)
            self.session.add(g)
            return {"ok": True, "detalle": f"factura extraída del correo → pendiente (cif {g.cif_emisor})"}
        # 2 · Hay importe pero faltan datos (típicamente el CIF) → rellenar y quedarse en revisar.
        if res.datos and float(res.datos.get("total") or 0) > 0:
            self._rellenar_parcial(g, res.datos)
            return {"ok": True, "detalle": f"datos del correo (falta CIF) total={res.datos.get('total')} → revisar"}
        # 3 · No hay factura legible en el correo → clasificar el sobre.
        clase, motivo = self._clasificar_detalle(email)
        if clase == Clasificacion.FACTURA:
            return {"ok": False, "detalle": "factura sin datos en el correo (en el portal): se queda en revisar"}
        sub = "no_factura" if clase == Clasificacion.NO_FACTURA else "falta_documento_portal"
        out = self._marcar_no_factura(g, f"{sub}:{motivo}",
                                      remitente=email.get("remitente"), asunto=email.get("asunto"))
        self.mover_etiqueta(email.get("uid"), ETIQUETA_INCIDENCIAS)
        out["detalle"] = f"{clase.value}:{motivo}"
        return out

    def _rellenar_parcial(self, g: Gasto, datos: dict) -> None:
        """Datos del correo SIN dar la factura por fiable (falta CIF o importes no cuadran): se queda
        en 'revisar' con los importes ya puestos para que el revisor solo teclee lo que falte."""
        self._volcar_datos(g, datos)
        # Motivo real: o falta el CIF del emisor, o los importes no cuadran (p.ej. retención de IRPF).
        g.incidencia = "datos_correo_falta_cif" if not datos.get("cif") else "datos_correo_revisar_importes"
        g.fiable = False
        self.session.add(g)

    def _bucket_e(self, g: Gasto) -> dict:
        """Consenur con suplido: rellena el suplido implícito (con guard) y deja la factura fiable."""
        vi = v.validar_importes(g.base_imponible, g.iva_pct, g.total,
                                suplido=g.suplido, retencion=g.retencion)
        sug = vi.get("suplido_sugerido")
        if g.suplido and g.suplido > 0:
            return {"ok": True, "detalle": "ya tenía suplido"}
        if sug is None:
            g.incidencia = "suplido_no_detectado"
            self.session.add(g)
            return {"ok": False, "detalle": "no se detecta suplido válido (guard 0.01<r<base*2)"}
        g.suplido = Decimal(str(sug))
        g.fiable = True
        g.incidencia = None
        # Consenur SÍ tiene CIF, pero impreso en VERTICAL → el OCR no lo capta. Es proveedor
        # conocido: rellenamos el CIF real (B86208824) para que la factura pase el control de
        # coherencia como cualquier otra, en vez de saltárselo (sin_cif_con_iva → revisar).
        if not g.cif_emisor:
            g.cif_emisor = "B86208824"
        if g.estado == "revisar":
            g.estado = "pendiente"
        self.session.add(g)
        return {"ok": True, "detalle": f"suplido={sug} → pendiente"}

    def _marcar_no_factura(self, g: Gasto, motivo: str, *, remitente: Optional[str] = None,
                           asunto: Optional[str] = None) -> dict:
        """Crea la gasto_incidencia y deja el gasto en 'no_factura' (no se borra el dato)."""
        self.registrar_incidencia(motivo, Fuente(
            gmail_message_id=g.gmail_message_id, fecha=g.fecha,
            remitente=remitente or g.proveedor_extraido, asunto=asunto or g.concepto), commit=False)
        g.estado = "no_factura"
        g.incidencia = motivo[:200]
        g.fiable = True
        self.session.add(g)
        return {"ok": True, "detalle": motivo}
