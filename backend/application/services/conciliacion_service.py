"""Motor de conciliación banco ↔ factura (capa de aplicación).

Reemplaza el trabajo manual: al pasarle los apuntes del Debe sin factura, para cada uno
  1) intenta CASAR una factura ya existente (GestoriaService.asociar_facturas_auto),
  2) si es un RECURRENTE conocido (alquiler, parking, colaborador, impuesto/SS/seguro) GENERA el
     documento + gasto y lo enlaza,
  3) el resto va a una BANDEJA DE REVISIÓN.

Idempotente y con dry-run (execute=False = solo diagnóstico). Reutilizable desde endpoint + scheduler.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from application.services import documento_pdf as pdfdoc
from application.services.gestoria_service import GestoriaService, es_pago_no_bancario
from domain.models.config import Integracion
from domain.models.economico import FormaPago, Pago
from domain.models.gestoria import Gasto, MovimientoBancario, movimiento_sin_factura
from domain.services.forma_pago import forma_pago_desde_apunte
from domain.models.identidad import Usuario
from infrastructure.external_apis import drive_client

MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
MELERO = dict(nombre="Aureliano Melero Ponce de León", dni="289.369-Y",
              domicilio="Mayor, 19   28921- ALCORCÓN (Madrid)")


def _norm(s: Optional[str]) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", " ", s)


def _iniciales(nombre: str, apellidos: str) -> str:
    n = (nombre or "").split()[0][:1]
    aps = "".join(p[0] for p in (apellidos or "").split() if p.lower() not in ("de", "la", "del", "las", "los"))
    return (n + aps).upper()


def _num_contrato_melero(y: int, m: int) -> str:
    idx = y * 12 + m
    n = idx - (2024 * 12 + 8) + 1 if idx >= 2024 * 12 + 8 else idx - (2019 * 12 + 8) + 1
    return f"{n:02d}/60"


class ConciliacionService:
    def __init__(self, session: Session, centro_id: int) -> None:
        self.session = session
        self.centro_id = centro_id
        self._cfg = None
        self._colab = None

    # ── apoyos ──
    def _drive(self) -> Optional[dict]:
        if self._cfg is None:
            ig = self.session.exec(select(Integracion).where(
                Integracion.centro_id == self.centro_id, Integracion.tipo == "google_drive")).first()
            self._cfg = (ig.config or {}) if ig else {}
        return self._cfg

    def _colaboradores(self) -> dict:
        """Registro de colaboradores por tokens de nombre → datos fiscales (para autofacturas)."""
        if self._colab is None:
            from domain.models.identidad import UserCenterRole  # noqa: F401
            out = {}
            try:
                from domain.models.gestoria import Deuda  # noqa
                from sqlmodel import text
                rows = self.session.exec(text(
                    "SELECT u.nombre,u.apellidos,u.nif,c.irpf_pct,c.aplica_irpf,c.num_colegiado "
                    "FROM usuarios u JOIN usuario_periodos up ON up.usuario_id=u.id "
                    "JOIN colaboradores c ON c.periodo_id=up.id")).all()
            except Exception:  # raiz: consulta SQL de colaboradores falla (esquema ausente) → mapa vacío
                rows = []
            for nombre, apellidos, nif, irpf_pct, aplica, coleg in rows:
                key = _norm(f"{nombre} {apellidos}").split()
                out[(nombre or "").strip().lower()] = dict(
                    nombre=f"{nombre} {apellidos}".title(), nif=nif,
                    irpf=float(irpf_pct) / 100 if (aplica and irpf_pct) else 0.0,
                    coleg=coleg, ini=_iniciales(nombre, apellidos), tokens=key)
            self._colab = out
        return self._colab

    def _subir(self, nombre: str, pdf: bytes) -> Optional[str]:
        cfg = self._drive()
        if not drive_client.configurado(cfg):
            return None
        try:
            r = drive_client.subir(cfg, filename=nombre, content=pdf, mime="application/pdf",
                                   folder_id=cfg.get("carpeta_facturas"))
            return r.get("url")
        except Exception:  # raiz: subida a Drive falla → sin URL, la factura se guarda igual
            return None

    def _alta(self, m, *, proveedor, numero, total, base, iva_pct=Decimal("0"), irpf=Decimal("0"),
              cif=None, categoria="Proveedores", concepto=None, pdf_bytes=None, pdf_name=None) -> Gasto:
        url = self._subir(pdf_name, pdf_bytes) if pdf_bytes else None
        # Identidad del proveedor = CIF, por el resolver único (nunca a mano, nunca por nombre).
        # Sin CIF válido devuelve None y la factura se queda con el nombre en texto, que es
        # el comportamiento querido: al directorio solo entra quien tiene identificación fiscal.
        from domain.services.proveedor_resolver import resolver_proveedor
        pid = resolver_proveedor(self.session, self.centro_id, proveedor, cif)
        g = Gasto(centro_id=self.centro_id, fecha=m.fecha_operacion, proveedor_extraido=proveedor,
                  proveedor_id=pid,
                  cif_emisor=cif, numero_factura=numero, concepto=concepto,
                  base_imponible=base, iva_pct=iva_pct, retencion=irpf, total=total,
                  estado="pagada", fiable=True, categoria=categoria, archivo_pdf_url=url,
                  incidencia="generado_conciliacion", movimiento_id=m.id,
                  forma_pago=forma_pago_desde_apunte(m.concepto_util))
        self.session.add(g); self.session.flush()
        m.estado_concil = "conciliado"; self.session.add(m)
        return g

    # ── clasificación de un apunte ──
    def _tipo(self, concepto: str):
        c = _norm(concepto)
        if "melero" in c or "aurelia" in c:
            return "alquiler"
        if "estacionamiento" in c or "garaje" in c:
            return "parking"
        # BNP Paribas Lease = RENTING de la impresora (arrendamiento de equipo): la cuota COMPLETA es
        # gasto deducible; NO se desglosa interés/principal (eso es solo para préstamos financieros).
        if "bnp" in c or "paribas" in c:
            return "renting"
        # IVA (mod. 303) → NEUTRO, no es gasto → a revisión, no se contabiliza.
        # (por texto; los nº de modelo colisionan con años/importes, p.ej. "2025" contiene "202")
        if "iva" in c:
            return "iva"
        # Impuesto de Sociedades (+ pagos/abonos a cuenta, mod. 202) e IBI → GASTO propio.
        if any(k in c for k in ("sociedad", "bienes inmuebles", " ibi")):
            return "impuesto"
        # Retenciones IRPF (mod. 111/115/190; ret. inm. urbanos; ret. ing. a cta.) → se REFLEJA como
        # retención liquidada a Hacienda (el líquido ya salió con el IRPF descontado; esto NO duplica).
        if any(k in c for k in ("irpf", "retenc", "inm urban", "ret inm")):
            return "retencion"
        if "impuesto" in c or "aeat" in c:
            return "impuesto"
        # Préstamo/leasing → solo el INTERÉS es gasto (el principal es capital) → a revisión (necesita desglose).
        if any(k in c for k in ("prestamo", "leasing")):
            return "prestamo"
        if any(k in c for k in ("tgss", "cotizacion", "seguridad social")):
            return "ss"
        if any(k in c for k in ("zurich", "santander vida", " vida ", "seguro")):
            return "seguro"
        for nom, p in self._colaboradores().items():
            if p["tokens"] and all(t in c for t in p["tokens"][:2]):
                return ("colaborador", p)
        return None

    # ── generadores por tipo ──
    def _gen_alquiler(self, m) -> Optional[str]:
        total = round(abs(float(m.importe)), 2)
        if total < 1000:
            return None  # ajuste pequeño → revisión
        base = round(total / 1.02, 2); irpf = round(base * 0.19, 2)
        numero = _num_contrato_melero(m.fecha_operacion.year, m.fecha_operacion.month)
        fecha = m.fecha_operacion.replace(day=1)
        if self.session.exec(select(Gasto).where(Gasto.centro_id == self.centro_id,
                Gasto.cif_emisor == "00289369Y", Gasto.numero_factura == numero, Gasto.fecha == fecha)).first():
            return "dup"
        pdf = pdfdoc.recibo_alquiler(numero, fecha.strftime("%d-%m-%Y"), base,
                                     MELERO["nombre"], MELERO["domicilio"], MELERO["dni"])
        self._alta(m, proveedor=f"{MELERO['nombre']} (arrendador)", numero=numero, total=Decimal(str(total)),
                   base=Decimal(str(base)), iva_pct=Decimal("21"), irpf=Decimal(str(irpf)), cif="00289369Y",
                   categoria="Alquiler", pdf_bytes=pdf, pdf_name=f"Melero_{numero.replace('/','-')}_{fecha}.pdf")
        return "alquiler"

    def _gen_parking(self, m) -> Optional[str]:
        total = round(abs(float(m.importe)), 2)
        numero = f"GAR{m.fecha_operacion.strftime('%Y%m')}"
        if self.session.exec(select(Gasto).where(Gasto.centro_id == self.centro_id, Gasto.numero_factura == numero)).first():
            return "dup"
        base = round(total / 1.21, 2)
        pdf = pdfdoc.factura_generica(numero, m.fecha_operacion.strftime("%d-%m-%Y"),
                                      "Estacionamientos y Garajes Virgen Bl.", None, "Alquiler plaza de garaje", total, 0.21)
        self._alta(m, proveedor="Estacionamientos y Garajes Virgen Bl.", numero=numero, total=Decimal(str(total)),
                   base=Decimal(str(base)), iva_pct=Decimal("21"), categoria="Alquiler",
                   concepto="Alquiler plaza de garaje", pdf_bytes=pdf, pdf_name=f"{numero}_Garaje.pdf")
        return "parking"

    def _gen_renting(self, m) -> Optional[str]:
        """Renting de la impresora (BNP Paribas Lease): cuota fija mensual → gasto deducible completo."""
        total = round(abs(float(m.importe)), 2)
        numero = f"BNP{m.fecha_operacion.strftime('%Y%m')}"
        if self.session.exec(select(Gasto).where(Gasto.centro_id == self.centro_id, Gasto.numero_factura == numero)).first():
            return "dup"
        base = round(total / 1.21, 2)
        concepto = f"Renting impresora (BNP Paribas Lease) — {MESES[m.fecha_operacion.month]} {m.fecha_operacion.year}"
        pdf = pdfdoc.factura_generica(numero, m.fecha_operacion.strftime("%d-%m-%Y"),
                                      "BNP Paribas Lease Group S.A.", None, concepto, total, 0.21)
        self._alta(m, proveedor="BNP Paribas Lease Group S.A.", numero=numero, total=Decimal(str(total)),
                   base=Decimal(str(base)), iva_pct=Decimal("21"), categoria="Renting",
                   concepto=concepto, pdf_bytes=pdf, pdf_name=f"{numero}_Renting_impresora.pdf")
        return "renting"

    # Meses tal como los escribe el banco en el concepto (con y sin tilde, enteros y abreviados).
    _MES_RE = {
        1: r"ene(?:ro)?", 2: r"feb(?:rero)?", 3: r"mar(?:zo)?", 4: r"abr(?:il)?",
        5: r"may(?:o)?", 6: r"jun(?:io)?", 7: r"jul(?:io)?", 8: r"ago(?:sto)?",
        9: r"sep(?:t)?(?:iembre)?", 10: r"oct(?:ubre)?", 11: r"nov(?:iembre)?", 12: r"dic(?:iembre)?",
    }

    def _periodo_producido(self, m) -> tuple[int, int, bool]:
        """Mes que se está liquidando, leído del propio concepto del banco.

        La autofactura de un colaborador se numera por el mes PRODUCIDO, no por el día en
        que se hace la transferencia: "Producción Noviembre" pagada el 22/12 es la de
        noviembre. Numerar por la fecha del pago dejaba toda la serie corrida un mes.

        Devuelve (año, mes, varios). `varios` avisa de que el concepto nombra más de un mes
        ("Producción Febrero y Marzo"): es un pago unificado y la autofactura única que sale
        de aquí hay que repartirla a mano. Si el concepto no dice ningún mes, se cae a la
        fecha del pago, que es el comportamiento de siempre."""
        txt = "".join(c for c in unicodedata.normalize("NFD", (m.concepto_util or "").lower())
                      if unicodedata.category(c) != "Mn")
        # Solo se leen los meses que van DETRÁS de "produccion": el resto del concepto
        # (nombres, referencias) no debe poder colarse como si fuera un periodo.
        corte = txt.find("produccion")
        if corte == -1:
            return m.fecha_operacion.year, m.fecha_operacion.month, False
        cola = txt[corte + len("produccion"):]
        hallados = sorted({mes for mes, pat in self._MES_RE.items()
                           if re.search(rf"\b{pat}\b", cola)})
        if not hallados:
            return m.fecha_operacion.year, m.fecha_operacion.month, False
        mes = hallados[0]
        # Un mes posterior al del pago solo puede ser del año anterior (diciembre cobrado en enero).
        anyo = m.fecha_operacion.year - 1 if mes > m.fecha_operacion.month else m.fecha_operacion.year
        return anyo, mes, len(hallados) > 1

    def _gen_colaborador(self, m, p) -> Optional[str]:
        base = round(abs(float(m.importe)), 2)
        if p["irpf"] > 0:
            base = round(base / (1 - p["irpf"]), 2)
        irpf = round(base * p["irpf"], 2)
        # Numeración: iniciales + año + mes (IGS202601). Si al colaborador se le paga MÁS DE
        # UNA VEZ en el mismo mes (pasa: una nómina y una liquidación de producción), el
        # número chocaba y la 2ª autofactura NO se generaba —quedaba un pago real sin su
        # justificante fiscal—. Ahora se numera en serie: IGS202601, IGS202601-2, …
        # Es seguro: `cuadrar` solo procesa apuntes SIN gasto asociado, así que un número
        # nuevo aquí siempre corresponde a un pago nuevo, nunca a una re-ejecución.
        anyo_p, mes_p, varios = self._periodo_producido(m)
        base_num = f"{p['ini']}{anyo_p}{mes_p:02d}"
        numero, orden = base_num, 1
        while self.session.exec(select(Gasto).where(
                Gasto.centro_id == self.centro_id, Gasto.numero_factura == numero)).first():
            orden += 1
            if orden > 50:      # freno de seguridad: algo raro pasa, no numerar sin fin
                return "dup"
            numero = f"{base_num}-{orden}"
        concepto = f"Servicios profesionales odontológicos — {MESES[mes_p]} {anyo_p}"
        pdf = pdfdoc.autofactura(numero, m.fecha_operacion.strftime("%d-%m-%Y"), p["nombre"], p["nif"],
                                 p["coleg"], base, p["irpf"], concepto)
        g = self._alta(m, proveedor=p["nombre"], numero=numero, total=Decimal(str(round(abs(float(m.importe)), 2))),
                       base=Decimal(str(base)), irpf=Decimal(str(irpf)), cif=p["nif"], categoria="Colaboradores",
                       concepto=concepto, pdf_bytes=pdf, pdf_name=f"{numero}_{p['nombre'].split()[0]}.pdf")
        if varios:
            # El banco liquidó varios meses de una vez: sale UNA autofactura, pero contablemente
            # son varias. Se marca para que aparezca en 'revisar' y el usuario la reparta.
            g.estado = "revisar"
            g.incidencia = "pago_unificado: el concepto del banco nombra más de un mes; repartir en varias facturas"
            self.session.add(g)
        return "colaborador"

    def renumerar_autofacturas(self, cif: str, *, execute: bool = False,
                               desde: Optional[date] = None) -> dict:
        """Re-numera las autofacturas de un colaborador por el mes PRODUCIDO.

        Las emitidas antes de arreglar `_periodo_producido` llevan el mes en que se hizo la
        transferencia, con lo que toda la serie va corrida. Aquí se recalcula con la MISMA
        función que usa el motor al generarlas —una sola regla, no dos— a partir del concepto
        del apunte al que están conciliadas.

        `execute=False` devuelve la propuesta sin tocar nada. El renombrado real va en dos
        pasadas (primero a un nombre temporal) para que dos facturas no choquen al cruzarse.

        `desde` acota a los pagos posteriores a esa fecha: un ejercicio ya presentado no se
        toca sin decidirlo expresamente, aunque su numeración venga del error antiguo."""
        gastos = [g for g in self.session.exec(select(Gasto).where(
            Gasto.centro_id == self.centro_id, Gasto.cif_emisor == cif,
            Gasto.movimiento_id.is_not(None))).all()]
        if desde:
            fechas = {m.id: m.fecha_operacion for m in self.session.exec(select(MovimientoBancario).where(
                MovimientoBancario.id.in_([g.movimiento_id for g in gastos])))} if gastos else {}
            gastos = [g for g in gastos if fechas.get(g.movimiento_id) and fechas[g.movimiento_id] >= desde]
        movs = {m.id: m for m in self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.id.in_([g.movimiento_id for g in gastos])))} if gastos else {}
        ini = "".join(w[0] for w in (gastos[0].proveedor_extraido or "").split()[:3]).upper() if gastos else ""

        propuesta, usados = [], {}
        for g in sorted(gastos, key=lambda x: (movs[x.movimiento_id].fecha_operacion, x.id)):
            m = movs[g.movimiento_id]
            anyo, mes, varios = self._periodo_producido(m)
            prefijo = (g.numero_factura or ini)[:3] if g.numero_factura else ini
            base_num = f"{prefijo}{anyo}{mes:02d}"
            usados[base_num] = usados.get(base_num, 0) + 1
            nuevo = base_num if usados[base_num] == 1 else f"{base_num}-{usados[base_num]}"
            if nuevo != g.numero_factura:
                propuesta.append({"id": g.id, "de": g.numero_factura, "a": nuevo,
                                  "pagada": str(m.fecha_operacion),
                                  "concepto": (m.concepto_banco or "")[-40:],
                                  "variosMeses": varios})
        if execute and propuesta:
            for c in propuesta:                       # 1ª pasada: nombres temporales
                self.session.get(Gasto, c["id"]).numero_factura = f"~TMP{c['id']}"
            self.session.flush()
            for c in propuesta:                       # 2ª pasada: número definitivo
                self.session.get(Gasto, c["id"]).numero_factura = c["a"]
            self.session.commit()
        return {"analizadas": len(gastos), "cambios": len(propuesta),
                "aplicado": bool(execute and propuesta), "detalle": propuesta}

    def reemitir_autofacturas(self, cif: str, *, desde: Optional[date] = None) -> dict:
        """Vuelve a emitir el PDF de las autofacturas de un colaborador con sus datos ACTUALES.

        El PDF se genera una sola vez, al conciliar. Si después cambia el número (por una
        renumeración) o el importe (por repartir un pago unificado), el documento archivado
        se queda mintiendo: dice un número o una cifra que ya no son los de la factura.
        Esto lo regenera desde la factura viva, que es la fuente de la verdad."""
        gastos = self.session.exec(select(Gasto).where(
            Gasto.centro_id == self.centro_id, Gasto.cif_emisor == cif,
            Gasto.categoria == "Colaboradores")).all()
        if desde:
            gastos = [g for g in gastos if g.fecha and g.fecha >= desde]
        colab = next((c for c in self._colaboradores().values() if c["nif"] == cif), None)
        if not colab:
            return {"emitidas": 0, "error": f"No hay colaborador con NIF {cif} en la ficha de personal."}
        emitidas, fallos = [], []
        for g in sorted(gastos, key=lambda x: (x.fecha or date.min, x.id)):
            base = float(g.base_imponible or 0)
            irpf_pct = (float(g.retencion) / base) if base else 0.0
            pdf = pdfdoc.autofactura(g.numero_factura or f"#{g.id}",
                                     g.fecha.strftime("%d-%m-%Y") if g.fecha else "",
                                     colab["nombre"], colab["nif"], colab["coleg"],
                                     base, irpf_pct, g.concepto or "Servicios profesionales odontológicos")
            url = self._subir(f"{g.numero_factura or g.id}_{colab['nombre'].split()[0]}.pdf", pdf)
            if url:
                g.archivo_pdf_url = url
                self.session.add(g)
                emitidas.append(g.numero_factura)
            else:
                fallos.append(g.numero_factura)
        self.session.commit()
        return {"emitidas": len(emitidas), "numeros": emitidas,
                "sinSubir": fallos}   # sin Drive configurado no se archiva: se dice, no se calla

    def _contabiliza(self, m, categoria, proveedor, cif=None) -> str:
        self._alta(m, proveedor=proveedor, numero=None, total=Decimal(str(round(abs(float(m.importe)), 2))),
                   base=None, cif=cif, categoria=categoria, concepto=(m.concepto_banco or "")[:120])
        return categoria

    # ── bandeja de revisión: apuntes que la herramienta NO puede cerrar sola y de los que PIDE un dato ──
    def pendientes_revision(self) -> dict:
        """Apuntes que el motor dejó a la espera de un dato del usuario (hoy: interés de préstamos/leasing).
        Es la cola que alimenta la UI 'Revisión': la herramienta lo pide, no lo inventa."""
        rows = self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.centro_id == self.centro_id,
            MovimientoBancario.estado_concil == "requiere_datos",
            MovimientoBancario.importe < 0,   # préstamos = salidas (Debe); nunca liquidaciones (Haber)
            movimiento_sin_factura()).order_by(MovimientoBancario.fecha_operacion)).all()
        return {"data": [{
            "movimientoId": m.id, "fecha": str(m.fecha_operacion),
            "concepto": (m.concepto_banco or "")[:120], "importe": round(abs(float(m.importe)), 2),
            "pide": "interes",
            "motivo": ("Préstamo/leasing: solo el interés es gasto (el principal amortiza capital y no es "
                       "deducible). Informa el interés del cuadro de amortización del recibo."),
        } for m in rows]}

    def resolver_prestamo(self, movimiento_id: int, interes: float) -> dict:
        """El usuario informa el interés del recibo → se contabiliza SOLO el interés como gasto financiero
        (deducible); el principal queda como amortización de capital (no deducible) y el apunte se concilia."""
        m = self.session.get(MovimientoBancario, movimiento_id)
        if not m or m.centro_id != self.centro_id:
            raise ValueError("Apunte no encontrado")
        total = round(abs(float(m.importe)), 2)
        interes = round(float(interes), 2)
        if interes < 0 or interes > total:
            raise ValueError(f"El interés debe estar entre 0 y {total:.2f} €")
        principal = round(total - interes, 2)
        concepto = (f"Interés de préstamo/leasing — {(m.concepto_banco or '')[:70]} · "
                    f"principal amortizado {principal:.2f} € (capital, no deducible)")
        g = Gasto(centro_id=self.centro_id, fecha=m.fecha_operacion, proveedor_extraido="Entidad financiera",
                  concepto=concepto, base_imponible=Decimal(str(interes)), iva_pct=Decimal("0"),
                  total=Decimal(str(interes)), estado="pagada", fiable=True,
                  categoria="Gastos financieros", incidencia="desglose_prestamo", movimiento_id=m.id,
                  forma_pago=forma_pago_desde_apunte(m.concepto_util))
        self.session.add(g); self.session.flush()
        m.estado_concil = "conciliado"; self.session.add(m)
        self.session.commit()
        return {"ok": True, "gastoId": g.id, "interes": interes, "principal": principal}

    # ── conciliación de tarjeta: liquidaciones del TPV ↔ pagos con tarjeta ──
    @staticmethod
    def _batch_date(mov) -> date:
        """Fecha del LOTE que liquida el apunte ('Liquidación efectuada el DD/MM/AAAA'). Si no se
        puede leer, se usa el día anterior al abono (el TPV liquida el lote del día previo)."""
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", mov.concepto_banco or "")
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:  # raiz: fecha imposible → vale el día previo al abono
                pass
        return mov.fecha_operacion - timedelta(days=1)

    @staticmethod
    def _subset(pares: list, objetivo: int, band: int, tol: int = 50):
        """Subconjunto de `pares` [(id, céntimos)] cuya suma S ∈ [objetivo−tol, objetivo+band] y
        minimiza |S−objetivo| (la liquidación = cobros − comisión, así que S suele ser ≥ objetivo).
        DP sobre céntimos; devuelve (ids, suma) o None."""
        hi = objetivo + band
        alcanz = {0: []}   # suma_céntimos → índices testigo
        for i, (_pid, c) in enumerate(pares):
            for suma in list(alcanz.keys()):
                ns = suma + c
                if ns <= hi and ns not in alcanz:
                    alcanz[ns] = alcanz[suma] + [i]
        cand = [s for s in alcanz if objetivo - tol <= s <= hi]
        if not cand:
            return None
        best = min(cand, key=lambda s: abs(s - objetivo))
        return ([pares[i][0] for i in alcanz[best]], best)

    def conciliar_tarjetas(self, *, execute: bool = False) -> dict:
        """Casa cada 'Liquidación efectuada el…' con el lote de pagos con tarjeta que la compone
        (ventana de fechas + tolerancia de comisión) y marca esos pagos como liquidados. Las
        liquidaciones sin pagos suficientes se marcan 'faltan pagos por registrar' con el importe."""
        res = {"execute": execute, "liquidaciones": 0, "conciliadas": 0, "pagos_marcados": 0,
               "comision_total": 0.0, "sin_cuadre": 0, "huecos": []}
        liqs = self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.centro_id == self.centro_id, MovimientoBancario.importe > 0,
            MovimientoBancario.concepto_banco.ilike("LIQUIDACION EFECTUADA%"),
            MovimientoBancario.estado_concil != "conciliado",
        ).order_by(MovimientoBancario.fecha_operacion)).all()
        usados: set[int] = set()   # pagos ya asignados en esta pasada (para que el dry-run sea realista)
        for mov in liqs:
            res["liquidaciones"] += 1
            A = int(round(float(mov.importe) * 100))
            D = self._batch_date(mov)
            cand = self.session.exec(select(Pago).where(
                Pago.centro_id == self.centro_id, Pago.anulado == False, Pago.liquidado == False,  # noqa: E712
                Pago.liquidacion_mov_id.is_(None),
                Pago.forma_pago_id.in_(select(FormaPago.id).where(FormaPago.grupo == "Tarjeta")),
                Pago.fecha >= D - timedelta(days=2), Pago.fecha <= D + timedelta(days=1),
            ).order_by(Pago.fecha)).all()
            cand = [p for p in cand if p.id not in usados]
            pares = [(p.id, int(round(float(p.importe) * 100))) for p in cand]
            pool = sum(c for _, c in pares)
            band = max(100, int(round(A * 0.02)))   # comisión TPV: hasta ~2% o 1 €
            match = self._subset(pares, A, band)
            if match:
                ids, suma = match
                usados.update(ids)
                res["conciliadas"] += 1
                res["pagos_marcados"] += len(ids)
                res["comision_total"] += (suma - A) / 100
                if execute:
                    idset = set(ids)
                    for p in cand:
                        if p.id in idset:
                            p.liquidado = True; p.liquidacion_mov_id = mov.id; self.session.add(p)
                    mov.estado_concil = "conciliado"; self.session.add(mov); self.session.commit()
            elif pool < A - 50:   # el lote no llega al importe → faltan cobros por registrar
                usados.update(p for p, _ in pares)
                res["pagos_marcados"] += len(pares)
                res["huecos"].append({"cobro": str(mov.fecha_operacion), "lote": str(D),
                                      "liquidacion": round(A / 100, 2), "cubierto": round(pool / 100, 2),
                                      "falta": round((A - pool) / 100, 2), "pagosEnLote": len(pares)})
                if execute:
                    for p in cand:
                        p.liquidado = True; p.liquidacion_mov_id = mov.id; self.session.add(p)
                    # estado propio (NO 'requiere_datos', que es la bandeja de préstamos)
                    mov.estado_concil = "falta_pagos"
                    mov.categoria = "Liquidación TPV (faltan pagos)"
                    self.session.add(mov); self.session.commit()
            else:                 # hay saldo de sobra pero ningún subconjunto limpio → revisar a mano
                res["sin_cuadre"] += 1
        res["comision_total"] = round(res["comision_total"], 2)
        return res

    # ── entrada pública ──
    # Lock consultivo de Postgres por centro. El motor se lanza desde la web (subida de extracto,
    # botón Cuadrar) y esas peticiones caen en cualquiera de los 4 workers: el 11-ago y el
    # 14-oct-2026 dos ejecuciones simultáneas comprobaron "¿existe ya esta autofactura?" antes
    # de que la otra la guardase y generaron 177 duplicadas (< 1 s entre copias). El lock
    # del scheduler no lo cubre: solo protege los jobs programados.
    _LOCK_CONCILIACION = 918_273_700

    @staticmethod
    def _propone_borrar(g) -> bool:
        """Efectivo y tarjeta personal de Juan A. son Debe sin apunte (la propia factura es el Debe):
        no se proponen. Excepción: las autofacturas de colaborador (categoría 'Colaboradores') que
        constan con esa tarjeta; son honorarios que se pagan por transferencia, nunca una compra."""
        if not es_pago_no_bancario(g.forma_pago):
            return True
        return g.categoria == "Colaboradores" and "manzanedo" in _norm(g.forma_pago)

    def facturas_sin_debe(self) -> dict:
        """PROPUESTA de facturas a eliminar: justificantes que ningún Debe ha reclamado.

        Regla del usuario: cada Debe (apunte de banco o pago en efectivo) tiene UN justificante; el
        camino va del Debe a la factura. Una factura sin Debe asociado sobra, pero solo se propone
        cuando el MES de la factura ya está cerrado (los Debe de todo el mes están subidos: hay algún
        apunte posterior a ese mes). Solo PROPONE: borrar lo decide el superuser (endpoint aparte).
        El pago en efectivo no se propone: ahí la propia factura es el Debe."""
        ultimo = self.session.exec(
            select(MovimientoBancario.fecha_operacion).where(MovimientoBancario.centro_id == self.centro_id)
            .order_by(MovimientoBancario.fecha_operacion.desc()).limit(1)).first()
        if not ultimo:
            return {"mes_cerrado_hasta": None, "total": 0, "importe": 0.0, "data": []}
        corte = ultimo.replace(day=1)                      # meses estrictamente anteriores = completos
        filas = self.session.exec(
            select(Gasto).where(Gasto.centro_id == self.centro_id, Gasto.movimiento_id.is_(None),
                                Gasto.fecha < corte)
            .order_by(Gasto.fecha, Gasto.id)).all()
        data = [{"id": g.id, "fecha": str(g.fecha), "numeroFactura": g.numero_factura,
                 "proveedor": g.proveedor_extraido, "total": float(g.total or 0),
                 "formaPago": g.forma_pago, "estado": g.estado, "fiable": g.fiable}
                for g in filas if self._propone_borrar(g)]
        return {"mes_cerrado_hasta": str(corte - timedelta(days=1)), "total": len(data),
                "importe": round(sum(d["total"] for d in data), 2), "data": data}

    def cuadrar(self, *, execute: bool = False, solo_ids: Optional[list[int]] = None) -> dict:
        if not execute:
            return self._cuadrar(execute=False, solo_ids=solo_ids)
        bind = self.session.get_bind()
        if bind.dialect.name != "postgresql":   # tests (SQLite): no hay locks consultivos
            return self._cuadrar(execute=True, solo_ids=solo_ids)
        conn = bind.raw_connection()   # conexión propia: el lock no se suelta con los commit()
        try:
            cur = conn.cursor()
            cur.execute("SELECT pg_try_advisory_lock(%s, %s)", (self._LOCK_CONCILIACION, self.centro_id))
            if not cur.fetchone()[0]:
                # Misma forma que una ejecución normal (la UI lee generadas/contabilizadas), a cero.
                vacio = self._cuadrar(execute=False, solo_ids=[])
                vacio.update(execute=True, ocupado=True, detalle=[
                    "Ya hay una conciliación en marcha para este centro; no se lanza otra a la vez."])
                return vacio
            try:
                return self._cuadrar(execute=True, solo_ids=solo_ids)
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s, %s)", (self._LOCK_CONCILIACION, self.centro_id))
        finally:
            conn.close()

    def _cuadrar(self, *, execute: bool = False, solo_ids: Optional[list[int]] = None) -> dict:
        res = {"execute": execute, "conciliadas_existentes": 0,
               "generadas": {"alquiler": 0, "parking": 0, "colaborador": 0, "renting": 0},
               "contabilizadas": {"impuesto": 0, "retencion": 0, "ss": 0, "seguro": 0},
               "revision": 0, "requiere_datos": 0, "detalle": []}
        # IVA (mod. 303) = neutro → revisión pasiva. Préstamo/leasing = solo el interés es gasto → la
        # herramienta lo aparca en 'requiere_datos' y PIDE el interés (no lo inventa).
        # 1) casar facturas ya existentes (solo en modo ejecutar)
        if execute:
            res["conciliadas_existentes"] = GestoriaService(self.session).asociar_facturas_auto(self.centro_id).get("asociados", 0)
        # 2) recurrentes sobre lo que sigue sin factura.
        #    `solo_ids` acota el motor a unos apuntes concretos: lo usa la importación de
        #    extractos para generar la factura de lo RECIÉN subido sin remover el histórico
        #    (ejercicios ya cerrados). Sin él, barre todo lo pendiente (uso del botón/cron).
        stmt_libres = select(MovimientoBancario).where(
            MovimientoBancario.centro_id == self.centro_id, MovimientoBancario.importe < 0,
            movimiento_sin_factura())
        if solo_ids is not None:
            if not solo_ids:
                return res
            stmt_libres = stmt_libres.where(MovimientoBancario.id.in_(solo_ids))
        libres = self.session.exec(stmt_libres.order_by(MovimientoBancario.fecha_operacion)).all()
        for m in libres:
            tipo = self._tipo(m.concepto_banco or "")
            fam = tipo[0] if isinstance(tipo, tuple) else tipo
            if fam == "prestamo":               # el motor lo aparca y PEDIRÁ el interés (bandeja de revisión)
                if execute:
                    m.estado_concil = "requiere_datos"; m.categoria = "Préstamo"
                    self.session.add(m); self.session.commit()
                res["requiere_datos"] += 1
                continue
            if not fam or fam == "iva":          # sin regla, o IVA neutro → revisión pasiva
                res["revision"] += 1
                continue
            if not execute:  # dry-run: solo cuenta
                if fam in res["generadas"]:
                    res["generadas"][fam] += 1
                elif fam in res["contabilizadas"]:
                    res["contabilizadas"][fam] += 1
                continue
            try:
                if fam == "alquiler":
                    r = self._gen_alquiler(m)
                elif fam == "parking":
                    r = self._gen_parking(m)
                elif fam == "renting":
                    r = self._gen_renting(m)
                elif fam == "colaborador":
                    r = self._gen_colaborador(m, tipo[1])
                elif fam == "impuesto":
                    r = self._contabiliza(m, "Impuestos", "Agencia Estatal de Administración Tributaria", "Q2826000H")
                elif fam == "retencion":   # retención IRPF liquidada a Hacienda (se refleja, NO duplica)
                    r = self._contabiliza(m, "Retenciones IRPF", "Agencia Estatal de Administración Tributaria", "Q2826000H")
                elif fam == "ss":
                    r = self._contabiliza(m, "Seguros Sociales", "Tesorería General de la Seguridad Social")
                elif fam == "seguro":
                    r = self._contabiliza(m, "Seguros", "(según recibo)")
                else:
                    r = None
                if r in (None, "dup"):
                    self.session.rollback(); res["revision"] += 1; continue
                self.session.commit()
                if r in res["generadas"]:
                    res["generadas"][r] += 1
                elif r in ("Impuestos", "Retenciones IRPF", "Seguros Sociales", "Seguros"):
                    key = {"Impuestos": "impuesto", "Retenciones IRPF": "retencion",
                           "Seguros Sociales": "ss", "Seguros": "seguro"}[r]
                    res["contabilizadas"][key] += 1
            except Exception:  # raiz: un apunte no debe tumbar el motor
                self.session.rollback(); res["revision"] += 1
        return res
