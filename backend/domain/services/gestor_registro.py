"""De la lectura de una factura a su registro.

Aquí se decide qué se hace con lo leído: registrarla, apartarla por no ser factura, o
dejarla en revisión. Y se guarda sin duplicar ni la factura ni el proveedor.

Ninguna decisión se toma con datos que no vengan del documento. Si falta algo esencial
—el emisor, el total, la fecha— la factura NO se registra a medias: va a revisión con el
texto leído, para que una persona la resuelva.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from domain.services import gestor_lectura_fiscal as fiscal

# Las tres cajas. Cada documento acaba en UNA.
REGISTRADA = "registrada"
DESCARTE = "descarte"
REVISION = "revision"


@dataclass
class Lectura:
    """Lo que el motor ha entendido de un documento."""

    caja: str
    motivo: Optional[str] = None
    id_fiscal: Optional[str] = None
    proveedor: Optional[str] = None
    numero: Optional[str] = None
    fecha: Optional[date] = None
    base: Optional[Decimal] = None
    iva: Optional[Decimal] = None
    irpf: Optional[Decimal] = None
    total: Optional[Decimal] = None
    cuadra: bool = False
    desvio: Optional[str] = None
    numero_reconstruido: bool = False
    texto: str = ""
    fichero: dict[str, Any] = field(default_factory=dict)

    @property
    def registrable(self) -> bool:
        return self.caja == REGISTRADA


def leer_factura(texto: str, propias: list[str],
                 fichero: Optional[dict[str, Any]] = None) -> Lectura:
    """Interpreta un documento ya convertido en texto y decide en qué caja va.

    El orden de las comprobaciones es deliberado: primero si es una factura, luego si se
    identifica al emisor y por último si las cifras cuadran. Así el motivo que se informa
    es el PRIMERO que impide registrarla, que es el que hay que resolver.
    """
    fichero = fichero or {}

    if not fiscal.es_documento_contable(texto, str(fichero.get("name") or ""), propias):
        return Lectura(caja=DESCARTE, motivo="no_contable", texto=texto,
                       fichero=fichero)

    id_fiscal = fiscal.emisor(texto, propias)
    proveedor = fiscal.denominacion_emisor(texto)
    fecha_iso = fiscal.fecha_emision(texto)

    # El número se busca en el DOCUMENTO. Solo si ahí no aparece —porque el OCR no pudo
    # leer la cabecera— se recurre al nombre del fichero, donde una persona lo escribió
    # al archivarlo. Se marca como reconstruido para que se sepa de dónde salió.
    numero = fiscal.numero_factura(texto)
    del_nombre = False
    if not numero:
        numero = fiscal.numero_del_nombre(fichero.get("name"))
        del_nombre = bool(numero)
    importes = fiscal.importes(texto)
    cuadre = fiscal.cuadre(importes["base"], importes["iva"],
                           importes["total"], importes.get("irpf"))

    lectura = Lectura(
        caja=REVISION,
        id_fiscal=id_fiscal,
        proveedor=proveedor,
        numero=numero,
        fecha=date.fromisoformat(fecha_iso) if fecha_iso else None,
        base=importes["base"],
        iva=importes["iva"],
        irpf=importes.get("irpf"),
        total=importes["total"],
        cuadra=cuadre["cuadra"],
        desvio=cuadre.get("desvio"),
        numero_reconstruido=del_nombre,
        texto=texto,
        fichero=fichero,
    )

    # Sin CIF no se registra. La identidad de un proveedor es su identificador fiscal:
    # dos empresas pueden llamarse casi igual, y el nombre lo escribe el OCR. Con solo
    # el nombre acabarían fusionadas en un mismo registro vacío — que es justo lo que
    # pasó al probarlo: dos proveedores sin CIF chocaron entre sí.
    if not id_fiscal:
        lectura.motivo = "sin_emisor"
        return lectura
    if not numero:
        lectura.motivo = "sin_numero"
        return lectura
    if not lectura.fecha:
        lectura.motivo = "sin_fecha"
        return lectura
    if not cuadre["cuadra"]:
        lectura.motivo = cuadre["motivo"]
        return lectura

    lectura.caja = REGISTRADA
    return lectura


# ─────────────────────────── guardado ───────────────────────────

def registrar(sesion, centro_id: int, lectura: Lectura) -> dict[str, Any]:
    """Guarda la factura y su proveedor, sin duplicar ninguno de los dos.

    · El PROVEEDOR se identifica por su CIF, nunca por el nombre: 'Laboratorio Dental
      Ortosol Sl' y 'Ortosol S.l' son el mismo si comparten identificador fiscal.
    · La FACTURA se identifica por (emisor, número, fecha, total): el mismo documento
      puede llegar dos veces —por correo y por Drive— y no debe contarse dos veces.

    Devuelve qué se hizo, para poder informarlo sin adivinar.
    """
    from sqlmodel import select

    from domain.models.gestor_ia import FacturaGestor, ProveedorGestor

    if not lectura.registrable:
        return {"accion": "no_registrable", "motivo": lectura.motivo}

    id_fiscal = fiscal.normalizar_identificacion(lectura.id_fiscal) or ""
    if not id_fiscal:
        return {"accion": "no_registrable", "motivo": "sin_emisor"}

    # Cada factura se guarda en su propio punto de retorno: si una falla —un dato
    # inesperado, una restricción de la tabla— se descarta ELLA y el resto del lote
    # sigue. Sin esto, un solo error abortaba la transacción entera y no se guardaba
    # ninguna de las 60 facturas del barrido.
    punto = sesion.begin_nested()
    try:
        resultado = _guardar(sesion, centro_id, lectura, id_fiscal)
        punto.commit()
        return resultado
    except Exception as fallo:  # raiz: factura con dato inesperado/restricción → se descarta solo ella, sigue el lote
        punto.rollback()
        return {"accion": "error", "motivo": str(fallo)[:120]}


def _guardar(sesion, centro_id: int, lectura: Lectura, id_fiscal: str) -> dict[str, Any]:
    """El guardado en sí. Lo envuelve `registrar`, que aísla los fallos."""
    from sqlmodel import select

    from domain.models.gestor_ia import FacturaGestor, ProveedorGestor

    # ── proveedor ──
    proveedor = None
    if id_fiscal:
        proveedor = sesion.exec(select(ProveedorGestor).where(
            ProveedorGestor.centro_id == centro_id,
            ProveedorGestor.id_fiscal == id_fiscal)).first()
    if proveedor is None:
        proveedor = ProveedorGestor(
            centro_id=centro_id,
            id_fiscal=id_fiscal,
            nombre=(lectura.proveedor or id_fiscal)[:200],
        )
        sesion.add(proveedor)
        sesion.flush()
        alta_proveedor = True
    else:
        # Si el proveedor se dio de alta solo con su CIF y ahora se conoce su nombre,
        # se completa. Nunca se sobrescribe un nombre por otro.
        if lectura.proveedor and proveedor.nombre == proveedor.id_fiscal:
            proveedor.nombre = lectura.proveedor[:200]
        alta_proveedor = False

    # ── factura: ¿ya estaba? ──
    existente = sesion.exec(select(FacturaGestor).where(
        FacturaGestor.centro_id == centro_id,
        FacturaGestor.id_fiscal == id_fiscal,
        FacturaGestor.numero_factura == (lectura.numero or "")[:60],
        FacturaGestor.fecha_emision == lectura.fecha,
        FacturaGestor.total == lectura.total)).first()
    if existente is not None:
        return {"accion": "duplicada", "factura_id": existente.id,
                "proveedor_id": proveedor.id}

    factura = FacturaGestor(
        centro_id=centro_id,
        numero_factura=(lectura.numero or "")[:60],
        fecha_emision=lectura.fecha,
        proveedor_nombre=(lectura.proveedor or proveedor.nombre)[:200],
        id_fiscal=id_fiscal,
        base_total=lectura.base or Decimal("0"),
        total=lectura.total or Decimal("0"),
        irpf_cuota=lectura.irpf or Decimal("0"),
        irpf_pct=Decimal("0"),
        iva_desglose=[{"cuota": str(lectura.iva or 0)}],
        divisa="EUR",
        estado="registrada",
        origen_dato="drive",
        reconstruida=lectura.numero_reconstruido,
        # El identificador del documento en su origen. Es UNIQUE en la tabla, así que
        # también protege de registrar dos veces el mismo fichero.
        gmail_message_id=f"drive:{lectura.fichero.get('id', '')}"[:120],
        drive_file_id=str(lectura.fichero.get("id") or "")[:120] or None,
        proveedor_id=proveedor.id,
    )
    sesion.add(factura)
    sesion.flush()
    return {"accion": "registrada", "factura_id": factura.id,
            "proveedor_id": proveedor.id, "alta_proveedor": alta_proveedor}


def anotar(sesion, centro_id: int, lectura: Lectura) -> dict[str, Any]:
    """Guarda lo que NO se registra: la revisión o el descarte.

    Una factura que no se puede registrar no desaparece: queda anotada **con el texto
    leído**, que es lo que permite resolverla después sin volver a pasar el OCR. Un
    descarte queda con su motivo, para poder comprobar que no se descartó nada bueno.
    """
    from sqlmodel import select

    from domain.models.gestor_ia import DescarteGestor, RevisionGestor

    referencia = f"drive:{lectura.fichero.get('id', '')}"[:120]
    nombre = str(lectura.fichero.get("name") or "")[:300]

    punto = sesion.begin_nested()
    try:
        if lectura.caja == DESCARTE:
            ya = sesion.exec(select(DescarteGestor).where(
                DescarteGestor.gmail_message_id == referencia)).first()
            if ya is not None:
                punto.commit()
                return {"accion": "descarte_ya_anotado", "id": ya.id}
            fila = DescarteGestor(
                centro_id=centro_id, gmail_message_id=referencia, asunto=nombre,
                motivo=lectura.motivo or "no_es_factura",
                detalle="el documento no se identifica como factura",
            )
        else:
            ya = sesion.exec(select(RevisionGestor).where(
                RevisionGestor.gmail_message_id == referencia)).first()
            if ya is not None:
                punto.commit()
                return {"accion": "revision_ya_anotada", "id": ya.id}
            fila = RevisionGestor(
                centro_id=centro_id, gmail_message_id=referencia, asunto=nombre,
                motivo=lectura.motivo or "revision",
                detalle=(f"desvío {lectura.desvio}" if lectura.desvio else None),
                origen_dato="drive",
                campos={
                    "id_fiscal": lectura.id_fiscal,
                    "proveedor": lectura.proveedor,
                    "numero": lectura.numero,
                    "fecha": lectura.fecha.isoformat() if lectura.fecha else None,
                    "base": str(lectura.base) if lectura.base is not None else None,
                    "iva": str(lectura.iva) if lectura.iva is not None else None,
                    "irpf": str(lectura.irpf) if lectura.irpf is not None else None,
                    "total": str(lectura.total) if lectura.total is not None else None,
                },
                # El texto ya leído: resolver la revisión no debe costar otro OCR.
                texto_leido=lectura.texto[:60000],
                intentos=1, resuelta=False,
            )
        sesion.add(fila)
        sesion.flush()
        punto.commit()
        return {"accion": f"{lectura.caja}_anotada", "id": fila.id}
    except Exception as fallo:  # raiz: fallo al guardar esta factura → rollback del savepoint, sigue el lote
        punto.rollback()
        return {"accion": "error", "motivo": str(fallo)[:120]}


def nombre_en_drive(lectura: Lectura, numero_interno: int) -> str:
    """El nombre con que se archiva el PDF:

        2023-08-31_17_ORTOSOL_2023-01606.pdf
        └─ fecha    └─ nº interno
                       └─ proveedor  └─ nº de factura

    La fecha va delante para que el archivo quede ordenado cronológicamente por nombre,
    que es como se revisa. El proveedor se acorta y se limpia de acentos y símbolos
    porque el nombre es también una ruta.
    """
    fecha = lectura.fecha.isoformat() if lectura.fecha else "sin-fecha"

    proveedor = fiscal.normalizar(lectura.proveedor or lectura.id_fiscal or "SIN-NOMBRE")
    proveedor = fiscal._FORMA_JURIDICA.sub("", proveedor)      # fuera S.L., S.A.…
    proveedor = re.sub(r"[^A-Z0-9 ]", " ", proveedor)
    proveedor = "-".join(proveedor.split())[:40].strip("-") or "SIN-NOMBRE"

    numero = re.sub(r"[^A-Za-z0-9._/-]", "", lectura.numero or "sin-numero")
    numero = numero.replace("/", "-")[:40]

    return f"{fecha}_{numero_interno}_{proveedor}_{numero}.pdf"


def archivar(cfg_drive: dict, lectura: Lectura, numero_interno: int,
             raiz_procesadas: str, carpeta_descartes: str) -> dict[str, Any]:
    """Mueve el PDF a su sitio en Drive y lo renombra según el patrón.

    · Registrada → `FACTURAS PROCESADAS/<año>/` con el nombre completo.
    · Descarte   → carpeta de descartes, conservando su nombre original.
    · Revisión   → **no se mueve**: se queda donde está, a la vista, hasta que alguien
      la resuelva. Esconder lo que falta es la forma más rápida de que no se arregle.
    """
    from domain.services import gestor_archivo as archivo

    file_id = str(lectura.fichero.get("id") or "")
    origen = str(lectura.fichero.get("_carpeta") or "")
    if not file_id or not origen:
        return {"archivado": False, "motivo": "sin_referencia_del_fichero"}

    if lectura.caja == REVISION:
        return {"archivado": False, "motivo": "queda_en_revision"}

    if lectura.caja == DESCARTE:
        movido = archivo.mover(cfg_drive, file_id, carpeta_descartes, origen)
        return {"archivado": movido, "destino": "descartes"}

    anio = lectura.fecha.strftime("%Y") if lectura.fecha else "sin-fecha"
    destino = archivo.carpeta_del_anio(cfg_drive, raiz_procesadas, anio)
    if not destino:
        return {"archivado": False, "motivo": "no_se_pudo_crear_la_carpeta_del_anio"}

    nombre = nombre_en_drive(lectura, numero_interno)
    archivo.renombrar(cfg_drive, file_id, nombre)
    movido = archivo.mover(cfg_drive, file_id, destino, origen)
    return {"archivado": movido, "destino": anio, "nombre": nombre}


def identificar_por_directorio(sesion, centro_id: int, lectura: Lectura) -> bool:
    """Intenta poner CIF a una factura cuyo emisor no se pudo leer, usando el directorio.

    Cuando el OCR pierde el CIF del emisor, el proveedor casi siempre ES CONOCIDO: otras
    facturas suyas sí se leyeron y está dado de alta con su identificador. El nombre del
    fichero lo delata (`..._PROCLINIC_0000216626.pdf`, `..._IMPLANT_PROTESIS_...`).

    Solo se acepta si **un único** proveedor del directorio encaja: con dos candidatos se
    deja en revisión. Poner el CIF equivocado sería atribuir un gasto a quien no es.
    """
    from sqlmodel import select

    from domain.models.gestor_ia import ProveedorGestor

    if lectura.id_fiscal:
        return False

    # Las palabras del nombre del fichero, sin la fecha ni el número interno.
    nombre = str(lectura.fichero.get("name") or "")
    base = re.sub(r"\.(pdf|png|jpe?g|tiff?)$", "", nombre, flags=re.I)
    partes = [p for p in base.split("_") if p and not re.fullmatch(r"\d{1,6}", p)
              and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", p)]
    pistas = {fiscal.normalizar(p) for p in partes if len(p) >= 4}
    if lectura.proveedor:
        pistas.add(fiscal.normalizar(lectura.proveedor))
    # También las razones sociales que aparezcan en el TEXTO de la factura: el nombre del
    # emisor suele estar en el cuerpo aunque el fichero se llame por su CIF o su número
    # (`..._B63568513_...`, `..._225_...`). Sin esto, el cruce se quedaba sin pistas.
    for linea in (lectura.texto or "").split("\n")[:40]:
        for m in fiscal._FORMA_JURIDICA.finditer(linea):
            antes = fiscal.normalizar(linea[:m.start()])
            palabras = [p for p in re.split(r"[^A-Z0-9]+", antes) if len(p) >= 4]
            if palabras:
                pistas.add(" ".join(palabras[-4:]))
    if not pistas:
        return False

    # La denominación leída del documento (aunque el OCR la deforme un poco) es la mejor
    # pista: 'IMPLANT PROPESIS DENTAL 2004' distingue al proveedor real de otro que solo
    # comparte una palabra ('IMPLANTOLOGÍA CAMPOS').
    palabras_pista: set[str] = set()
    for pista in pistas:
        palabras_pista |= {p for p in re.split(r"[^A-Z0-9]+", pista) if len(p) >= 4}

    puntuados: list[tuple[int, ProveedorGestor]] = []
    for proveedor in sesion.exec(select(ProveedorGestor).where(
            ProveedorGestor.centro_id == centro_id)).all():
        registrado = fiscal.normalizar(proveedor.nombre)
        if not registrado or registrado == proveedor.id_fiscal:
            continue
        palabras_reg = {p for p in re.split(r"[^A-Z0-9]+", registrado) if len(p) >= 4}
        # Puntúa cada palabra que coincide, tolerando la deformación del OCR (PROPESIS ~
        # PROTESIS).
        comunes = sum(1 for a in palabras_pista
                      for b in palabras_reg if fiscal._parecido(a, b))
        if comunes:
            puntuados.append((comunes, proveedor))

    if not puntuados:
        return False
    puntuados.sort(key=lambda x: -x[0])
    mejor, segundo = puntuados[0][0], (puntuados[1][0] if len(puntuados) > 1 else 0)
    # Se acepta si el mejor gana claramente (al menos 2 palabras en común y el doble que
    # el siguiente): así el proveedor correcto se distingue del que solo comparte una.
    if mejor >= 2 and mejor > segundo:
        lectura.id_fiscal = puntuados[0][1].id_fiscal
        lectura.proveedor = lectura.proveedor or puntuados[0][1].nombre
        return True

    candidatos = [p for n, p in puntuados if n == mejor]
    unicos = {p.id_fiscal for p in candidatos}
    if len(unicos) != 1:
        return False

    lectura.id_fiscal = candidatos[0].id_fiscal
    lectura.proveedor = lectura.proveedor or candidatos[0].nombre
    return True


def procesar(sesion, centro_id: int, texto: str, propias: list[str],
             fichero: dict[str, Any], cfg_drive: Optional[dict] = None,
             raiz_procesadas: str = "", carpeta_descartes: str = "") -> dict[str, Any]:
    """Un documento, de principio a fin: se lee, se decide, se guarda y se archiva.

    El archivado en Drive es opcional: sin `cfg_drive` el documento se registra pero no
    se mueve, que es lo que conviene mientras se afina el motor. El orden importa —
    primero la base de datos y solo después Drive—: si el archivado falla, la factura ya
    está registrada y el fichero sigue donde estaba, a la vista.
    """
    lectura = leer_factura(texto, propias, fichero)

    # Segunda oportunidad para las que solo fallan por el CIF del emisor.
    if lectura.motivo == "sin_emisor" and identificar_por_directorio(
            sesion, centro_id, lectura):
        lectura = leer_factura(texto, propias, fichero)
        if not lectura.id_fiscal:
            identificar_por_directorio(sesion, centro_id, lectura)
        if lectura.id_fiscal and lectura.numero and lectura.fecha and lectura.cuadra:
            lectura.caja, lectura.motivo = REGISTRADA, None
    resultado = (registrar(sesion, centro_id, lectura) if lectura.registrable
                 else anotar(sesion, centro_id, lectura))

    archivado: dict[str, Any] = {}
    if cfg_drive and raiz_procesadas:
        # El número interno es el id de la factura recién creada: correlativo, único y
        # ya guardado, así que el nombre del fichero y el registro apuntan al mismo sitio.
        interno = resultado.get("factura_id") or 0
        archivado = archivar(cfg_drive, lectura, interno,
                             raiz_procesadas, carpeta_descartes)

    return {"caja": lectura.caja, "motivo": lectura.motivo,
            "lectura": lectura, **resultado, **archivado}
