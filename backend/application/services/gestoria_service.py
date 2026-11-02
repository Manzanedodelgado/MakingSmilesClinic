"""GESTORÍA · modo FACTURACIÓN — gastos, banco, modelos, conciliación, envío.

Réplica de la Gestoría .37 (lado control de gasto). Lee/escribe tablas reales:
gastos · movimientos_bancarios · modelos_fiscales · documentos_admin · pagos.
"""
import csv
import io
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, func, select

from domain.models.config import Configuracion, Integracion
from domain.models.documentos import DocumentoAdmin
from domain.models.economico import Pago
from domain.models.gestoria import (Gasto, ModeloFiscal, MovimientoBancario, Proveedor,
                                    movimiento_sin_factura)
from domain.services.forma_pago import es_canonica, forma_pago_canonica
from infrastructure.external_apis import smtp_mailer


def _d(v) -> float:
    return round(float(v or 0), 2)


def _norm_txt(s: Optional[str]) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower())
                   if unicodedata.category(c) != "Mn")


def es_pago_no_bancario(forma: Optional[str]) -> bool:
    """True si la forma de pago NO pasa por la cuenta bancaria de la clínica → no hay apunte
    propio que conciliar: efectivo/metálico, o la tarjeta personal de Juan A. Manzanedo.
    Estas facturas se dan por conciliadas como 'apunte externo' (no entran en la auto-asociación)."""
    t = _norm_txt(forma)
    return bool(t) and ("efectivo" in t or "metalico" in t or "caja" in t or "manzanedo" in t)


# ───────── EXTRACTO BANCARIO: lectura multi-formato → filas (lista de listas) ─────────
def _filas_xlsx(contenido: bytes) -> list:
    import io

    import openpyxl
    # read_only=False a propósito: algunos bancos (Sabadell) declaran mal las dimensiones del .xlsx
    # y en read_only openpyxl devolvería 1 sola fila.
    wb = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True)
    return [list(f) for f in wb.active.iter_rows(values_only=True)]


def _filas_xls(contenido: bytes) -> list:
    import xlrd  # solo .xls antiguo; ImportError si no está → el caller avisa
    sh = xlrd.open_workbook(file_contents=contenido).sheet_by_index(0)
    return [sh.row_values(r) for r in range(sh.nrows)]


def _filas_csv(contenido: bytes) -> list:
    import csv
    import io
    texto = None
    for enc in ("utf-8-sig", "latin-1"):     # los bancos ES exportan en UTF-8 o ISO-8859-1
        try:
            texto = contenido.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        texto = contenido.decode("utf-8", "replace")
    muestra = "\n".join(texto.splitlines()[:20])
    delim = ";" if muestra.count(";") >= muestra.count(",") else ","   # ES suele usar ';'
    return list(csv.reader(io.StringIO(texto), delimiter=delim))


def _filas_pdf(contenido: bytes) -> list:
    """Extrae los movimientos de un extracto bancario en PDF (formato Santander).

    El PDF es una tabla de columnas fijas, pero el texto NO sale en orden de lectura
    (concepto, importe y fechas vienen entremezclados), así que se reconstruye por
    COORDENADAS: la fecha de operación —la columna más a la izquierda— ancla cada fila,
    y el resto de celdas se asignan por su posición horizontal. Las bandas de columna se
    midieron sobre extractos reales de Santander (ver x0 de cada columna abajo).

    Devuelve cabecera + filas, el MISMO formato que los otros lectores, para que
    `_importar_filas` las trate igual (cero duplicación del parser).
    """
    import re as _re
    try:
        import fitz  # PyMuPDF, ya usado en el proyecto para generar PDFs
    except ImportError:  # pragma: no cover
        raise ValueError("El lector de PDF no está disponible aquí. Sube el extracto en XLSX o CSV.")

    # Bandas de columna (x0 del texto). Fecha op. ≈25 · F.Valor ≈65 · concepto ≈135
    # · importe ≈420-445 (alineado a la derecha) · saldo ≈520.
    X_FECHA_OP_MAX = 55      # a la derecha de esto ya es la fecha valor, que se ignora
    X_CONCEPTO_MIN, X_CONCEPTO_MAX = 100, 400
    X_IMPORTE_MIN, X_IMPORTE_MAX = 400, 500
    X_SALDO_MIN = 500

    RE_FECHA = _re.compile(r"^\d{2}/\d{2}/\d{4}$")
    RE_NUM = _re.compile(r"^-?[\d.]+,\d{2}$")
    RE_IBAN = _re.compile(r"\bES\d{2}[\s\d]{18,26}")

    doc = fitz.open(stream=contenido, filetype="pdf")
    iban = ""
    filas = [["fecha", "concepto", "importe", "saldo"]]
    try:
        for pagina in doc:
            palabras = pagina.get_text("words")   # (x0, y0, x1, y1, palabra, ...)
            if not iban:
                m = RE_IBAN.search(pagina.get_text())
                if m:   # el match puede arrastrar espacios/saltos: dejar solo alfanuméricos
                    iban = _re.sub(r"[^A-Z0-9]", "", m.group(0).upper())[:34]
            # Anclas = fecha de operación en la columna de la izquierda, en orden vertical.
            anclas = sorted((w for w in palabras
                             if w[0] < X_FECHA_OP_MAX and RE_FECHA.match(w[4])),
                            key=lambda w: w[1])
            for i, ancla in enumerate(anclas):
                y_desde = ancla[1] - 3
                y_hasta = anclas[i + 1][1] - 3 if i + 1 < len(anclas) else float("inf")
                banda = [w for w in palabras if y_desde <= w[1] < y_hasta]
                concepto = " ".join(
                    w[4] for w in sorted((w for w in banda
                                          if X_CONCEPTO_MIN <= w[0] < X_CONCEPTO_MAX),
                                         key=lambda w: (round(w[1]), w[0])))
                importe = next((w[4] for w in banda
                                if X_IMPORTE_MIN <= w[0] < X_IMPORTE_MAX and RE_NUM.match(w[4])), None)
                saldo = next((w[4] for w in banda
                              if w[0] >= X_SALDO_MIN and RE_NUM.match(w[4])), None)
                if importe is None:      # fila sin importe = no es un apunte (cabeceras, pies)
                    continue
                filas.append([ancla[4], concepto.strip(), importe, saldo])
    finally:
        doc.close()

    if len(filas) == 1:
        raise ValueError("No se encontraron movimientos en el PDF. "
                         "¿Es un extracto bancario? Si no, expórtalo en XLSX o CSV.")
    if iban:   # el IBAN va en su propia columna para que `_importar_filas` lo recoja
        filas[0].append("iban")
        for f in filas[1:]:
            f.append(iban)
    return filas


def _filas_de_archivo(contenido: bytes, filename: str) -> list:
    """Extrae las filas de un extracto en los formatos comunes (.xlsx, .xls, .csv/.txt). Detecta
    por extensión y, si no la hay, por los magic bytes. Lanza ValueError con motivo si no se puede."""
    nombre = (filename or "").lower()
    if nombre.endswith((".csv", ".txt", ".tsv")):
        return _filas_csv(contenido)
    if nombre.endswith(".xls"):
        return _filas_xls(contenido)
    if nombre.endswith((".xlsx", ".xlsm")):
        return _filas_xlsx(contenido)
    if nombre.endswith(".pdf") or contenido[:4] == b"%PDF":
        return _filas_pdf(contenido)
    if contenido[:2] == b"PK":                                            # zip → xlsx
        return _filas_xlsx(contenido)
    if contenido[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":              # OLE2 → xls
        return _filas_xls(contenido)
    return _filas_csv(contenido)                                          # texto plano → csv


class GestoriaService:
    def __init__(self, session: Session):
        self.session = session

    # ───────── DASHBOARD ─────────
    def dashboard(self, centro_id: int, desde: date, hasta: date) -> dict:
        ingresos = self.session.exec(select(func.coalesce(func.sum(Pago.importe), 0)).where(
            Pago.centro_id == centro_id, Pago.anulado == False,  # noqa: E712
            Pago.fecha >= desde, Pago.fecha <= hasta)).one()
        gastos = self.session.exec(select(func.coalesce(func.sum(Gasto.total), 0)).where(
            Gasto.centro_id == centro_id, Gasto.fecha >= desde, Gasto.fecha <= hasta)).one()
        facturas = self.session.exec(select(func.count(DocumentoAdmin.id)).where(
            DocumentoAdmin.centro_id == centro_id, DocumentoAdmin.fecha >= desde,
            DocumentoAdmin.fecha <= hasta)).one()
        ing, gas = _d(ingresos), _d(gastos)
        return {"periodo": {"desde": str(desde), "hasta": str(hasta)},
                "ingresos": ing, "gastos": gas, "balance": round(ing - gas, 2),
                "facturasEmitidas": int(facturas or 0)}

    # ───────── FACTURAS EMITIDAS (documentos_admin) ─────────
    def facturas_emitidas(self, centro_id: int, *, anyo: Optional[int] = None,
                          search: Optional[str] = None, limit: int = 500) -> dict:
        stmt = select(DocumentoAdmin).where(
            DocumentoAdmin.centro_id == centro_id, DocumentoAdmin.num_doc.is_not(None))
        if anyo:
            stmt = stmt.where(DocumentoAdmin.anyo == anyo)
        if search:
            like = f"%{search}%"
            stmt = stmt.where((DocumentoAdmin.nombre.ilike(like)) | (DocumentoAdmin.apellidos.ilike(like))
                              | (DocumentoAdmin.nif.ilike(like)))
        total = self.session.exec(select(func.count()).select_from(stmt.subquery())).one()
        rows = self.session.exec(stmt.order_by(
            DocumentoAdmin.anyo.desc(), DocumentoAdmin.num_doc.desc()).limit(limit)).all()
        return {"total": int(total or 0), "data": [self._fact_dict(d) for d in rows]}

    @staticmethod
    def _fact_dict(d: DocumentoAdmin) -> dict:
        cli = " ".join(p for p in (d.nombre, d.apellidos) if p) or "—"
        estado = "anulada" if d.anulada else ("abono" if d.abonado else "emitida")
        return {"id": d.id, "numero": f"{d.serie or ''}{d.num_doc}", "fecha": str(d.fecha),
                "cliente": cli, "nif": d.nif, "concepto": d.concepto, "estado": estado,
                "verifactu": bool(d.hash_factura)}

    # ───────── GASTOS (facturas recibidas) ─────────
    def list_gastos(self, centro_id: int, *, estado: Optional[str] = None,
                    desde: Optional[date] = None, hasta: Optional[date] = None) -> dict:
        stmt = select(Gasto).where(Gasto.centro_id == centro_id)
        if estado:
            stmt = stmt.where(Gasto.estado == estado)
        if desde:
            stmt = stmt.where(Gasto.fecha >= desde)
        if hasta:
            stmt = stmt.where(Gasto.fecha <= hasta)
        rows = self.session.exec(stmt.order_by(Gasto.fecha.desc())).all()
        provs = {p.id: p.nombre for p in
                 self.session.exec(select(Proveedor).where(Proveedor.centro_id == centro_id)).all()}
        # Apunte bancario de cada factura (Gasto.movimiento_id). Un mismo apunte puede pagar
        # VARIAS facturas (pago unificado) → se cuenta cuántas cuelgan de cada uno para poder decirlo.
        mov_ids = {g.movimiento_id for g in rows if g.movimiento_id}
        movs = {m.id: m for m in self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.id.in_(mov_ids)))} if mov_ids else {}
        cuantas = dict(self.session.exec(
            select(Gasto.movimiento_id, func.count(Gasto.id))
            .where(Gasto.movimiento_id.in_(mov_ids))
            .group_by(Gasto.movimiento_id)).all()) if mov_ids else {}
        import urllib.parse

        def correo_url(mid):  # enlace al correo original en Gmail (cuando no hay PDF descargado)
            if mid and not mid.startswith("upload:"):
                return ("https://mail.google.com/mail/u/0/#search/rfc822msgid:"
                        + urllib.parse.quote(mid.strip("<>")))
            return None
        data = [{"id": g.id, "fecha": str(g.fecha), "proveedor": provs.get(g.proveedor_id) or g.proveedor_extraido,
                 "cifEmisor": g.cif_emisor, "incidencia": g.incidencia,
                 "concepto": g.concepto, "numeroFactura": g.numero_factura, "baseImponible": _d(g.base_imponible),
                 "ivaPct": _d(g.iva_pct), "retencion": _d(g.retencion), "suplido": _d(g.suplido),
                 "total": _d(g.total),
                 "divisa": g.divisa, "tipoDocumento": g.tipo_documento, "estado": g.estado,
                 "formaPago": g.forma_pago, "condicionesPago": g.condiciones_pago,
                 "archivoPdfUrl": g.archivo_pdf_url, "correoUrl": correo_url(g.gmail_message_id),
                 "movimientoId": g.movimiento_id,
                 "movimientoConcepto": (f"{movs[g.movimiento_id].fecha_operacion} · "
                                        f"{_d(movs[g.movimiento_id].importe)}€"
                                        if g.movimiento_id in movs else None),
                 # nº de facturas que comparten ese apunte: >1 ⇒ el pago fue unificado
                 "movimientoFacturas": cuantas.get(g.movimiento_id, 0) if g.movimiento_id else 0}
                for g in rows]
        return {"data": data, "kpis": {
            "total": len(rows), "totalGastos": round(sum(_d(g.total) for g in rows), 2),
            "pendiente": round(sum(_d(g.total) for g in rows if g.estado != "pagada"), 2)}}

    def asociar_gasto_movimiento(self, centro_id: int, gasto_id: int, movimiento_id: int) -> dict:
        """Vincula una factura con un apunte bancario del Debe.

        Una factura se paga con UN apunte, pero un apunte puede pagar VARIAS facturas
        (pago unificado: una transferencia que liquida varios meses). Lo único que no se
        admite es repartir más dinero del que movió el banco."""
        g = self._get(Gasto, gasto_id, centro_id)
        self._get(MovimientoBancario, movimiento_id, centro_id)  # 404 si no existe / otro centro
        # Lock pesimista del apunte: evita que dos peticiones concurrentes lean el mismo reparto
        # y ambas lo sobre-asignen. Re-leemos la fila ya bloqueada.
        m = self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.id == movimiento_id,
            MovimientoBancario.centro_id == centro_id).with_for_update()).one()
        if m.importe >= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se asocian apuntes del Debe (negativos).")
        ya = sum((o.total or Decimal("0")) for o in self.session.exec(select(Gasto).where(
            Gasto.centro_id == centro_id, Gasto.movimiento_id == movimiento_id,
            Gasto.id != gasto_id)).all())
        if ya + (g.total or Decimal("0")) > abs(m.importe):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"No cabe: el apunte movió {abs(m.importe):.2f} € y ya tiene "
                                f"{ya:.2f} € repartidos en otras facturas.")
        g.movimiento_id = movimiento_id
        # El extracto dice cómo se pagó de verdad. Solo se rellena si estaba vacío: lo que
        # el usuario haya escrito a mano manda sobre lo que deduzca la máquina.
        if not es_canonica(g.forma_pago):
            g.forma_pago = forma_pago_canonica(m.concepto_util) or g.forma_pago
        m.estado_concil = "conciliado"; self.session.add(m)
        self._sincronizar_estado(g, pagada=True); self.session.add(g)
        self.session.commit()
        return {"ok": True, "gastoId": gasto_id, "movimientoId": movimiento_id}

    def _sincronizar_estado(self, g, pagada: bool) -> None:
        """Estado del gasto derivado de los hechos (única regla):
        tiene apunte → 'pagada'; no es factura → se preserva; faltan datos o no es fiable → 'revisar';
        si no → 'pendiente'. Los tributos (sanción/liquidación) son gasto y NO exigen CIF."""
        if pagada:
            g.estado = "pagada"; return
        if g.estado == "no_factura":              # clasificado como no-factura: no se reabre por faltar datos
            return
        tipo = (g.tipo_documento or "").lower()
        emisor_n = (g.proveedor_extraido or "").lower()
        autoridad = any(k in emisor_n for k in ("agencia tributaria", "hacienda", "tesorer", "seguridad social", "aeat"))
        es_tributo = autoridad or tipo in ("sancion", "sanción", "autoliquidacion", "autoliquidación")
        falta = (not (g.total and abs(g.total) > 0)) or (not g.proveedor_extraido) or (not getattr(g, "fiable", True))
        if es_tributo:                            # impuesto: solo importa que tenga importe
            g.estado = "revisar" if not (g.total and abs(g.total) > 0) else "pendiente"; return
        # Sin identificación fiscal PERO cobra IVA → debería tener CIF: a revisar para teclearlo.
        # Sin CIF y exenta (IVA 0, extranjera) es válida → no se manda a revisar por eso.
        sin_cif_con_iva = (not g.cif_emisor) and bool(g.iva_pct and g.iva_pct > 0)
        g.estado = "revisar" if (falta or sin_cif_con_iva) else "pendiente"

    def asociar_facturas_auto(self, centro_id: int, dias: int = 30) -> dict:
        """Cuadra facturas con apuntes del Debe por importe EXACTO (tolerancia solo de
        redondeo). Decide con dos señales, NINGUNA obligatoria por sí sola: que el proveedor
        aparezca en el concepto del apunte, o que la fecha esté a menos de `dias` (máximo un
        mes natural, decisión del usuario 2026-08-09) — el concepto del banco no siempre
        trae el proveedor, así que esa señal nunca es determinante en solitario.
        Si la fecha de la factura es imposible (mal leída), se corrige con la del apunte."""
        import re as _re
        import unicodedata as _ud
        # Excluye las pagadas fuera del banco de la clínica (metálico / tarjeta externa de
        # Manzanedo): no tienen apunte propio → conciliadas como externas, no se auto-asocian.
        gastos = [g for g in self.session.exec(select(Gasto).where(
            Gasto.centro_id == centro_id, Gasto.total > 0,
            Gasto.movimiento_id.is_(None))).all()
            if not es_pago_no_bancario(g.forma_pago)]
        # El automático solo toca apuntes sin ninguna factura: repartir un apunte entre varias
        # es una decisión contable del usuario, no algo que la máquina deba adivinar.
        libres = self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.centro_id == centro_id, MovimientoBancario.importe < 0,
            movimiento_sin_factura())).all()
        # nombre canónico del proveedor (si el gasto está vinculado por proveedor_id)
        prov_nombre = {p.id: p.nombre for p in self.session.exec(select(Proveedor).where(
            Proveedor.centro_id == centro_id)).all()}
        _STOP = {"sa", "sau", "slu", "slp", "sociedad", "energia", "espagne", "espana",
                 "iberia", "group", "recibo", "concepto", "factura", "the", "and"}

        def _norm(s):
            s = "".join(c for c in _ud.normalize("NFD", (s or "").lower()) if _ud.category(c) != "Mn")
            return _re.sub(r"[^a-z0-9 ]", " ", s)

        def _prov_tokens(g):
            # nombre canónico si lo hay; si no, el extraído (tolerante a emails: orange@orange.es → orange)
            base = prov_nombre.get(g.proveedor_id) or g.proveedor_extraido or ""
            if "@" in base:
                base = base.split("@")[-1].rsplit(".", 1)[0].replace(".", " ")
            return [t for t in _norm(base).split() if len(t) >= 4 and t not in _STOP]

        def prov_en_concepto(g, m):
            concepto = _norm(m.concepto_banco)
            return any(t in concepto for t in _prov_tokens(g))

        usados: set = set()
        asociados = 0
        for g in sorted(gastos, key=lambda x: x.fecha):
            cands = [m for m in libres if m.id not in usados
                     and abs(abs(m.importe) - g.total) <= Decimal("0.01")]
            if not cands:
                continue
            # mejor candidato: primero por proveedor en el concepto, luego por fecha más cercana
            cands.sort(key=lambda m: (not prov_en_concepto(g, m), abs((m.fecha_operacion - g.fecha).days)))
            m = cands[0]
            prov_ok = prov_en_concepto(g, m)
            fecha_ok = abs((m.fecha_operacion - g.fecha).days) <= dias
            unico = len(cands) == 1
            # asociar si el proveedor coincide, o la fecha cuadra, o es el único con ese importe exacto
            if not (prov_ok or fecha_ok or unico):
                continue
            g.movimiento_id = m.id
            if not es_canonica(g.forma_pago):
                g.forma_pago = forma_pago_canonica(m.concepto_util) or g.forma_pago
            m.estado_concil = "conciliado"
            self.session.add(m)
            usados.add(m.id)
            # Fecha imposible (mal leída por OCR): se corrige con la del cargo bancario (dato
            # fiable) PERO se deja rastro en `incidencia` (valor viejo→nuevo); no se pierde el original.
            if g.fecha.year < 2018 or g.fecha.year > 2027:
                vieja = g.fecha
                g.fecha = m.fecha_operacion
                g.incidencia = (f"fecha_corregida_desde_banco: {vieja.isoformat()} → "
                                f"{m.fecha_operacion.isoformat()}")[:200]
            self._sincronizar_estado(g, pagada=True); self.session.add(g)
            asociados += 1
        self.session.commit()
        return {"asociados": asociados, "sinCoincidencia": len(gastos) - asociados,
                "facturasSinApunte": len(gastos)}

    def corregir_concepto_movimiento(self, centro_id: int, mid: int, texto: Optional[str]) -> dict:
        """Anota la lectura correcta de un apunte mal rotulado por el banco.

        NO toca `concepto_banco`: el extracto es el documento y se queda como está. Mandar
        texto vacío deshace la corrección y devuelve el apunte a lo que dice el banco."""
        m = self._get(MovimientoBancario, mid, centro_id)
        m.concepto_corregido = (texto or "").strip() or None
        self.session.add(m); self.session.commit()
        return {"ok": True, "id": m.id, "concepto": m.concepto_util,
                "original": m.concepto_banco, "corregido": bool(m.concepto_corregido)}

    def enlazar_proveedores(self, centro_id: int) -> dict:
        """Enlaza al directorio las facturas que traen CIF pero quedaron sin `proveedor_id`.

        Las generaba el motor de conciliación, que guardaba el nombre y el CIF pero no pasaba
        por el resolver, así que salían como "Proveedor sin identificar" aun sabiendo quiénes
        eran. Usa el MISMO resolver que todo lo demás: identidad por CIF, cero duplicados."""
        from domain.services.proveedor_resolver import resolver_proveedor
        rows = self.session.exec(select(Gasto).where(
            Gasto.centro_id == centro_id, Gasto.proveedor_id.is_(None),
            Gasto.cif_emisor.is_not(None))).all()
        enlazadas = 0
        for g in rows:
            pid = resolver_proveedor(self.session, centro_id, g.proveedor_extraido, g.cif_emisor)
            if pid:
                g.proveedor_id = pid
                self.session.add(g)
                enlazadas += 1
        self.session.commit()
        return {"revisadas": len(rows), "enlazadas": enlazadas,
                "sinCifValido": len(rows) - enlazadas}

    def completar_formas_pago(self, centro_id: int) -> dict:
        """Rellena la forma de pago de las facturas que tienen apunte y la traen vacía.

        No es un arreglo puntual: cada vez que entra un extracto nuevo hay facturas que se
        concilian y el dato pasa a ser conocido. Nunca pisa lo que haya escrito el usuario."""
        # TODAS las que no tengan ya una forma canónica, con apunte o sin él. El efectivo no
        # pasa por el banco: si solo se miraran las conciliadas, los pagos en metálico
        # quedarían para siempre como "EFECTIVO"/"METÁLICO"/"Efectivo", que es el mismo dato
        # escrito de cuatro maneras.
        rows = [g for g in self.session.exec(select(Gasto).where(
            Gasto.centro_id == centro_id)).all() if not es_canonica(g.forma_pago)]
        con_apunte = [g.movimiento_id for g in rows if g.movimiento_id]
        movs = {m.id: m for m in self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.id.in_(con_apunte)))} if con_apunte else {}
        puestas = normalizadas = 0
        for g in rows:
            # 1º el banco, que es un hecho; 2º el texto de la propia factura, que es lo que
            # el proveedor declaró. Nunca al revés.
            f = None
            if (m := movs.get(g.movimiento_id)):
                f = forma_pago_canonica(m.concepto_util)
                if f:
                    puestas += 1
            if not f and g.forma_pago:
                f = forma_pago_canonica(g.forma_pago)
                if f:
                    normalizadas += 1
            # Lo que no es una forma de pago no se tira: es el plazo o la cuenta que traía la
            # factura, y se guarda en su campo. Así la columna "Forma pago" deja de mentir.
            if not f and g.forma_pago and not g.condiciones_pago:
                g.condiciones_pago = g.forma_pago[:300]
            if f != g.forma_pago:
                g.forma_pago = f
                self.session.add(g)
        self.session.commit()
        return {"revisadas": len(rows), "desdeElBanco": puestas,
                "normalizadasDelTexto": normalizadas,
                "sinReconocer": len(rows) - puestas - normalizadas}

    def desasociar_gasto(self, centro_id: int, gasto_id: int) -> dict:
        g = self._get(Gasto, gasto_id, centro_id)
        mid, g.movimiento_id = g.movimiento_id, None
        if mid:
            # El apunte solo vuelve a 'abierto' si NO le queda ninguna otra factura colgando
            # (pago unificado: soltar una de las tres no lo deja sin conciliar).
            quedan = self.session.exec(select(Gasto).where(
                Gasto.centro_id == centro_id, Gasto.movimiento_id == mid)).first()
            if not quedan and (m := self.session.get(MovimientoBancario, mid)):
                m.estado_concil = "abierto"; self.session.add(m)
        self._sincronizar_estado(g, pagada=False); self.session.add(g)
        self.session.commit()
        return {"ok": True}

    def movimientos_debe_libres(self, centro_id: int) -> dict:
        """Apuntes del Debe aún no asociados a ninguna factura (para el desplegable de asociar)."""
        rows = self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.centro_id == centro_id, MovimientoBancario.importe < 0,
            movimiento_sin_factura()).order_by(MovimientoBancario.fecha_operacion.desc())).all()
        return {"data": [{"id": m.id, "label": f"{m.fecha_operacion} · {m.concepto_banco[:40]} · {_d(m.importe)}€"}
                         for m in rows]}

    def gastos_libres(self, centro_id: int) -> dict:
        """Facturas (gastos) sin apunte bancario asociado — para la conciliación MANUAL desde
        Debe/Haber, cuando el motor automático (asociar_facturas_auto) no encontró candidato
        y el apunte se queda en rojo. Mismas exclusiones que el motor: lo pagado fuera del
        banco (metálico, tarjeta externa) nunca tiene apunte propio que asociar."""
        rows = self.session.exec(select(Gasto).where(
            Gasto.centro_id == centro_id, Gasto.total > 0,
            Gasto.movimiento_id.is_(None))).all()
        rows = [g for g in rows if not es_pago_no_bancario(g.forma_pago)]
        provs = {p.id: p.nombre for p in self.session.exec(
            select(Proveedor).where(Proveedor.centro_id == centro_id)).all()}
        rows.sort(key=lambda g: g.fecha, reverse=True)
        return {"data": [{"id": g.id,
                          "label": f"{g.fecha} · {provs.get(g.proveedor_id) or g.proveedor_extraido or 'Sin proveedor'} · {_d(g.total)}€"}
                         for g in rows]}

    def create_gasto(self, centro_id: int, data: dict) -> dict:
        g = Gasto(centro_id=centro_id, proveedor_id=data.get("proveedor_id"), fecha=data["fecha"],
                  concepto=data.get("concepto"), numero_factura=data.get("numero_factura"),
                  base_imponible=Decimal(str(data.get("base_imponible", 0))),
                  iva_pct=Decimal(str(data.get("iva_pct", 0))),
                  retencion=Decimal(str(data.get("retencion", 0))),
                  suplido=Decimal(str(data.get("suplido", 0))),
                  total=Decimal(str(data.get("total", 0))),
                  forma_pago=data.get("forma_pago"),
                  estado=data.get("estado", "pendiente"))
        self.session.add(g); self.session.commit(); self.session.refresh(g)
        return {"id": g.id}

    def update_gasto(self, centro_id: int, gid: int, data: dict) -> dict:
        g = self._get(Gasto, gid, centro_id)
        for f in ("estado", "concepto", "numero_factura", "proveedor_extraido", "categoria",
                  "incidencia", "tipo_documento", "forma_pago", "divisa"):
            if f in data and data[f] is not None:
                setattr(g, f, data[f])
        for f in ("base_imponible", "iva_pct", "total", "retencion", "suplido"):
            if f in data and data[f] is not None:
                setattr(g, f, Decimal(str(data[f])))
        if data.get("fecha"):
            from datetime import datetime
            g.fecha = (data["fecha"] if isinstance(data["fecha"], date)
                       else datetime.strptime(str(data["fecha"])[:10], "%Y-%m-%d").date())
        # CIF del emisor (identidad fiscal): normalizar y, si es válido, vincular el proveedor por él.
        if "cif_emisor" in data:
            from domain.services.invoice_extractor import normalizar_cif
            cif = normalizar_cif(data.get("cif_emisor"))
            g.cif_emisor = cif
            if cif:                       # el revisor aportó la identidad → ya es fiable
                g.fiable = True
                g.incidencias = None
        # Vincular con el directorio: proveedor_id explícito, o por CIF (identidad), o nada.
        if "proveedor_id" in data:
            g.proveedor_id = data["proveedor_id"]
        elif g.cif_emisor:               # identidad = CIF: crea/enlaza el proveedor por su CIF
            from domain.services.proveedor_resolver import resolver_proveedor
            pid = resolver_proveedor(self.session, centro_id, data.get("proveedor_extraido") or g.proveedor_extraido, g.cif_emisor)
            if pid:
                g.proveedor_id = pid
        # Si el usuario corrige datos sin forzar estado, recalcula con el invariante único
        # (pagada si tiene apunte; revisar si faltan datos; pendiente si no).
        if "estado" not in data:
            self._sincronizar_estado(g, pagada=bool(g.movimiento_id))
            if g.estado != "revisar":
                g.incidencia = None
        self.session.add(g); self.session.commit()
        return {"id": g.id, "estado": g.estado, "total": _d(g.total)}

    def _match_o_crea_proveedor(self, centro_id: int, nombre: str) -> Optional[int]:
        from domain.services.proveedor_resolver import resolver_proveedor
        return resolver_proveedor(self.session, centro_id, nombre)

    def delete_gasto(self, centro_id: int, gid: int) -> dict:
        """Borra la factura y devuelve una instantánea de lo borrado (para la auditoría:
        un registro que solo diga el id de una fila ya inexistente no permite reconstruir nada)."""
        g = self._get(Gasto, gid, centro_id)
        snap = {"proveedor": g.proveedor_extraido, "cif": g.cif_emisor,
                "numeroFactura": g.numero_factura, "fecha": str(g.fecha),
                "total": _d(g.total), "estado": g.estado}
        self.session.delete(g); self.session.commit()
        return snap

    def duplicados_gastos(self, centro_id: int) -> dict:
        rows = self.session.exec(select(Gasto).where(Gasto.centro_id == centro_id)).all()
        seen: dict = {}
        dups = []
        for g in rows:
            k = (g.proveedor_extraido or g.proveedor_id, _d(g.total), str(g.fecha))
            if k in seen:
                dups.append({"id": g.id, "proveedor": g.proveedor_extraido, "numeroFactura": g.numero_factura,
                             "fecha": str(g.fecha), "base": _d(g.base_imponible), "iva": _d(g.iva_pct),
                             "total": _d(g.total)})
            seen[k] = True
        return {"data": dups}

    def contabilizacion(self, centro_id: int, anyo: Optional[int] = None) -> dict:
        """Contabilización robusta de gastos para el Resumen / modelo 303.

        El IVA se deriva de (total − base) SOLO cuando hay desglose con un tipo legal
        (≤22%). Las facturas sin base, con importes incoherentes o fuera de rango de
        fecha NO inflan el IVA: se cuentan aparte como pendientes de revisión.
        """
        stmt = select(Gasto).where(Gasto.centro_id == centro_id, Gasto.total > 0)
        rows = self.session.exec(stmt).all()
        trimestres: dict = {}   # (anyo, trim) → acumulado
        sin_desglose = incoherentes = 0
        sin_desglose_imp = Decimal("0")
        for g in rows:
            a = g.fecha.year
            if a < 2018 or a > 2027:
                incoherentes += 1
                continue
            if anyo and a != anyo:
                continue
            base, total = g.base_imponible or Decimal("0"), g.total or Decimal("0")
            sup = g.suplido or Decimal("0")
            neto = total - sup     # el suplido es exento: queda FUERA del cálculo del IVA soportado
            if g.estado == "revisar" or neto < base:
                incoherentes += 1
                continue
            if base <= 0:
                sin_desglose += 1
                sin_desglose_imp += total
                continue
            ratio = (neto - base) / base
            if ratio > Decimal("0.22"):
                incoherentes += 1
                continue
            k = (a, (g.fecha.month - 1) // 3 + 1)
            acc = trimestres.setdefault(k, {"facturas": 0, "base": Decimal("0"),
                                            "iva": Decimal("0"), "total": Decimal("0")})
            acc["facturas"] += 1
            acc["base"] += base
            acc["iva"] += neto - base
            acc["total"] += total
        data = [{"anyo": a, "trimestre": f"T{t}", "facturas": v["facturas"],
                 "base": _d(v["base"]), "ivaSoportado": _d(v["iva"]), "totalGasto": _d(v["total"])}
                for (a, t), v in sorted(trimestres.items(), reverse=True)]
        tot_base = sum((v["base"] for v in trimestres.values()), Decimal("0"))
        tot_iva = sum((v["iva"] for v in trimestres.values()), Decimal("0"))
        tot_gasto = sum((v["total"] for v in trimestres.values()), Decimal("0"))
        return {"data": data, "kpis": {
            "facturas": sum(v["facturas"] for v in trimestres.values()),
            "base": _d(tot_base), "ivaSoportado": _d(tot_iva), "totalGasto": _d(tot_gasto),
            "sinDesglose": sin_desglose, "sinDesgloseImporte": _d(sin_desglose_imp),
            "incoherentes": incoherentes}}

    # ───────── DIRECTORIO DE PROVEEDORES ─────────
    # Catálogo de categorías de gasto y formas de pago (config; el valor elegido vive en `proveedores`).
    CATEGORIAS_GASTO = [
        "SUMINISTROS Y REPARACIONES", "LABORATORIOS", "DEPOSITO", "COMPRAS", "ALQUILER",
        "MARKETING DIGITAL", "RRHH", "GESTORIA", "FINANCIACIONES", "IMPUESTOS", "BANCOS",
    ]
    FORMAS_PAGO = ["BANCO", "METALICO", "TRANSFERENCIA"]

    def catalogos_proveedor(self) -> dict:
        return {"categorias": self.CATEGORIAS_GASTO, "formasPago": self.FORMAS_PAGO}

    def proveedores_sin_categoria_count(self, centro_id: int) -> dict:
        """Recuento real (no aproximado) para el badge del icono de Proveedores — mismo criterio
        de 'sin categoría' que usa el propio directorio (categoria_defecto vacío o en blanco)."""
        n = self.session.exec(select(func.count(Proveedor.id)).where(
            Proveedor.centro_id == centro_id,
            (Proveedor.categoria_defecto.is_(None)) | (Proveedor.categoria_defecto == ""))).one()
        return {"count": int(n or 0)}

    def list_proveedores(self, centro_id: int) -> dict:
        """Directorio de proveedores (tabla `proveedores`), con el nº de facturas de cada uno."""
        provs = self.session.exec(select(Proveedor).where(
            Proveedor.centro_id == centro_id).order_by(Proveedor.nombre)).all()
        counts: dict = {}
        for pid in self.session.exec(select(Gasto.proveedor_id).where(
                Gasto.centro_id == centro_id, Gasto.proveedor_id.is_not(None))).all():
            counts[pid] = counts.get(pid, 0) + 1
        data = [{"id": p.id, "nombre": p.nombre, "cif": p.cif, "emailContacto": p.email_contacto,
                 "telefono": p.telefono, "direccion": p.direccion, "iban": p.iban,
                 "categoria": p.categoria_defecto, "formaPago": p.forma_pago_defecto,
                 "esLaboratorio": p.es_laboratorio, "numFacturas": counts.get(p.id, 0)} for p in provs]
        return {"data": data}

    def fusionar_proveedores(self, centro_id: int, canonico_id: int, otros_ids: list[int]) -> dict:
        """Fusiona varios proveedores en uno: reasigna sus facturas al canónico, hereda los
        datos que falten y borra los duplicados. Lo usa la herramienta de fusión del directorio."""
        canon = self._get(Proveedor, canonico_id, centro_id)
        n = 0
        for oid in {x for x in otros_ids if x != canonico_id}:
            p = self.session.get(Proveedor, oid)
            if not p or p.centro_id != centro_id:
                continue
            for g in self.session.exec(select(Gasto).where(Gasto.proveedor_id == oid)).all():
                g.proveedor_id = canonico_id; self.session.add(g)
            for attr in ("cif", "email_contacto", "telefono", "direccion", "iban",
                         "categoria_defecto", "forma_pago_defecto"):
                if not getattr(canon, attr) and getattr(p, attr):
                    setattr(canon, attr, getattr(p, attr))
            if p.es_laboratorio:
                canon.es_laboratorio = True
            self.session.add(canon); self.session.delete(p); n += 1
        self.session.commit()
        return {"ok": True, "fusionados": n, "canonicoId": canonico_id}

    def unificar_por_cif(self, centro_id: int) -> dict:
        """Regla única: la identificación fiscal manda. Fusiona los proveedores que comparten
        el MISMO CIF normalizado (nunca por nombre). El canónico es el de más facturas."""
        from domain.services.invoice_extractor import normalizar_cif
        provs = self.session.exec(select(Proveedor).where(Proveedor.centro_id == centro_id)).all()
        nf = {}
        for pid in self.session.exec(select(Gasto.proveedor_id).where(
                Gasto.centro_id == centro_id, Gasto.proveedor_id.is_not(None))).all():
            nf[pid] = nf.get(pid, 0) + 1
        grupos: dict = {}
        for p in provs:
            c = normalizar_cif(p.cif)
            if c:
                grupos.setdefault(c, []).append(p)
        fusionados = 0
        for g in grupos.values():
            if len(g) < 2:
                continue
            g = sorted(g, key=lambda p: nf.get(p.id, 0), reverse=True)
            res = self.fusionar_proveedores(centro_id, g[0].id, [p.id for p in g[1:]])
            fusionados += res["fusionados"]
        return {"ok": True, "fusionados": fusionados}

    def _propagar_categoria(self, centro_id: int, pid: int, categoria: Optional[str]) -> int:
        """La categoría de un proveedor es una decisión sobre EL PROVEEDOR, no sobre una factura
        suelta: al asignarla (a mano, en el directorio) se aplica retroactivamente a TODAS sus
        facturas ya registradas, no solo a las futuras — decisión del usuario, 2026-08-09."""
        if not categoria:
            return 0
        n = 0
        for g in self.session.exec(select(Gasto).where(
                Gasto.centro_id == centro_id, Gasto.proveedor_id == pid)).all():
            if g.categoria != categoria:
                g.categoria = categoria
                self.session.add(g)
                n += 1
        return n

    def crear_proveedor(self, centro_id: int, data: dict) -> dict:
        from domain.services.proveedor_resolver import resolver_proveedor
        from domain.services.invoice_extractor import normalizar_cif
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El nombre del proveedor es obligatorio.")
        if not normalizar_cif(data.get("cif")):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "El CIF/identificación fiscal es obligatorio (nacional o extranjero).")
        # Identidad = CIF: si ya existe ese CIF, NO duplica → actualiza ese.
        pid = resolver_proveedor(self.session, centro_id, nombre, data.get("cif"))
        p = self.session.get(Proveedor, pid)
        for campo, attr in (("email_contacto", "email_contacto"), ("telefono", "telefono"),
                            ("direccion", "direccion"), ("iban", "iban"),
                            ("categoria", "categoria_defecto"), ("forma_pago", "forma_pago_defecto")):
            if data.get(campo):
                setattr(p, attr, data[campo])
        if data.get("es_laboratorio"):
            p.es_laboratorio = True
        self.session.add(p)
        facturas_actualizadas = self._propagar_categoria(centro_id, p.id, p.categoria_defecto)
        self.session.commit()
        return {"id": p.id, "facturasActualizadas": facturas_actualizadas}

    def update_proveedor(self, centro_id: int, pid: int, data: dict) -> dict:
        from domain.services.invoice_extractor import normalizar_cif
        p = self._get(Proveedor, pid, centro_id)
        if "nombre" in data and data["nombre"]:
            p.nombre = data["nombre"].strip()[:200]
        for campo, attr in (("cif", "cif"), ("email_contacto", "email_contacto"),
                            ("telefono", "telefono"), ("direccion", "direccion"),
                            ("iban", "iban"), ("categoria", "categoria_defecto"),
                            ("forma_pago", "forma_pago_defecto")):
            if campo in data:
                setattr(p, attr, (data[campo] or None))
        if "es_laboratorio" in data:
            p.es_laboratorio = bool(data["es_laboratorio"])
        self.session.add(p)
        facturas_actualizadas = self._propagar_categoria(centro_id, p.id, p.categoria_defecto)
        self.session.commit()
        # El CIF manda: si al asignar el CIF coincide con otro proveedor, se fusionan.
        cif_n = normalizar_cif(p.cif)
        if cif_n:
            otro = self.session.exec(select(Proveedor).where(
                Proveedor.centro_id == centro_id, Proveedor.cif == cif_n,
                Proveedor.id != p.id)).first()
            if otro:
                # el canónico es el de más facturas
                na = len(self.session.exec(select(Gasto).where(Gasto.proveedor_id == p.id)).all())
                nb = len(self.session.exec(select(Gasto).where(Gasto.proveedor_id == otro.id)).all())
                canon, dup = (p, otro) if na >= nb else (otro, p)
                self.fusionar_proveedores(centro_id, canon.id, [dup.id])
                return {"id": canon.id, "fusionadoCon": dup.id, "facturasActualizadas": facturas_actualizadas}
        return {"id": p.id, "facturasActualizadas": facturas_actualizadas}

    def delete_proveedor(self, centro_id: int, pid: int) -> dict:
        """Borra el proveedor y desvincula sus facturas (conservan el nombre en proveedor_extraido)."""
        p = self._get(Proveedor, pid, centro_id)
        desvinculados = 0
        for g in self.session.exec(select(Gasto).where(
                Gasto.centro_id == centro_id, Gasto.proveedor_id == pid)).all():
            if not g.proveedor_extraido:
                g.proveedor_extraido = p.nombre
            g.proveedor_id = None
            self.session.add(g)
            desvinculados += 1
        self.session.delete(p); self.session.commit()
        return {"ok": True, "facturasDesvinculadas": desvinculados}

    # ───────── BANCO ─────────
    def list_movimientos(self, centro_id: int, *, tipo: Optional[str] = None,
                         anyo: Optional[int] = None) -> dict:
        """tipo: 'debe' (gastos, importe<0) | 'haber' (ingresos, importe>0) | None (todos)."""
        stmt = select(MovimientoBancario).where(MovimientoBancario.centro_id == centro_id)
        if tipo == "debe":
            stmt = stmt.where(MovimientoBancario.importe < 0)
        elif tipo == "haber":
            stmt = stmt.where(MovimientoBancario.importe >= 0)
        if anyo:
            stmt = stmt.where(MovimientoBancario.fecha_operacion >= date(anyo, 1, 1),
                              MovimientoBancario.fecha_operacion <= date(anyo, 12, 31))
        rows = self.session.exec(stmt.order_by(MovimientoBancario.fecha_operacion.desc())).all()

        # Datos REALES de la factura/pago asociado: el nº interno (#123) no dice nada al
        # usuario. Se resuelven en bloque (dos consultas), nunca una por fila (N+1).
        mov_ids = [m.id for m in rows]
        # Un apunte puede pagar VARIAS facturas (pago unificado) → se agrupan por apunte.
        por_mov: dict[int, list[Gasto]] = {}
        if mov_ids:
            for g in self.session.exec(select(Gasto).where(Gasto.movimiento_id.in_(mov_ids))):
                por_mov.setdefault(g.movimiento_id, []).append(g)
        gastos = {g.id: g for lst in por_mov.values() for g in lst}
        prov_ids = {g.proveedor_id for g in gastos.values() if g.proveedor_id}
        provs = {p.id: p.nombre for p in self.session.exec(
            select(Proveedor).where(Proveedor.id.in_(prov_ids)))} if prov_ids else {}
        pago_ids = {m.pago_id for m in rows if m.pago_id}
        pagos = {p.id: p for p in self.session.exec(
            select(Pago).where(Pago.id.in_(pago_ids)))} if pago_ids else {}

        def _asociado(m) -> Optional[dict]:
            """Referencia legible + si hay PDF descargable, para enlazar la factura real."""
            facts = sorted(por_mov.get(m.id, []), key=lambda g: (g.fecha or date.min, g.id))
            if facts:
                g = facts[0]
                base = {"tipo": "factura", "id": g.id,
                        # El directorio solo admite proveedores con CIF; sin él la factura
                        # guarda el nombre en texto. Enseñarlo es más útil (y más cierto)
                        # que decir "sin identificar" teniéndolo delante.
                        "proveedor": (provs.get(g.proveedor_id) or g.proveedor_extraido
                                      or "Proveedor sin identificar"),
                        "numero": g.numero_factura, "fecha": str(g.fecha) if g.fecha else None,
                        "total": _d(g.total), "tienePdf": bool(g.archivo_pdf_url)}
                if len(facts) > 1:
                    # Pago unificado: la transferencia liquidó varias facturas de golpe.
                    base["unificado"] = [
                        {"id": f.id, "numero": f.numero_factura,
                         "fecha": str(f.fecha) if f.fecha else None,
                         "total": _d(f.total), "tienePdf": bool(f.archivo_pdf_url)} for f in facts]
                    base["totalUnificado"] = round(sum(_d(f.total) for f in facts), 2)
                return base
            if m.pago_id and (p := pagos.get(m.pago_id)):
                return {"tipo": "pago", "id": p.id, "proveedor": None,
                        "numero": None, "fecha": str(p.fecha) if p.fecha else None,
                        "total": _d(p.importe), "tienePdf": False}
            return None

        data = [{"id": m.id, "fechaOperacion": str(m.fecha_operacion), "conceptoBanco": m.concepto_util,
                 # El literal del extracto se sigue enviando: la UI lo enseña como origen.
                 "conceptoOriginal": m.concepto_banco if m.concepto_corregido else None,
                 "importe": _d(m.importe), "categoria": m.categoria, "estadoConcil": m.estado_concil,
                 "tipo": "debe" if m.importe < 0 else "haber",
                 "gastoId": (por_mov.get(m.id) or [None])[0] and por_mov[m.id][0].id,
                 "pagoId": m.pago_id, "documentoAdminId": m.documento_admin_id,
                 "asociado": _asociado(m)}
                for m in rows]
        debe = sum((m.importe for m in rows if m.importe < 0), Decimal("0"))
        haber = sum((m.importe for m in rows if m.importe >= 0), Decimal("0"))
        return {"data": data, "kpis": {"total": len(rows), "debe": _d(debe), "haber": _d(haber),
                "saldo": _d(haber + debe)}}

    def crear_movimiento(self, centro_id: int, data: dict) -> dict:
        """Alta manual de un apunte (botón 'Nuevo' en Debe/Haber).

        Mismo criterio de duplicado que la importación (fecha + importe + concepto vía
        _mismo_concepto), pero SIN exigir el mismo IBAN: el modal manual no pide cuenta
        (se guarda como 'MANUAL'), así que comparar por IBAN nunca detectaría que ya existe
        el mismo apunte llegado por extracto real. Regla ABSOLUTA del usuario (2026-08-09):
        no puede haber dos apuntes con la misma fecha+concepto+importe, de ningún tipo."""
        importe = Decimal(str(data["importe"]))
        fecha = data["fecha_operacion"]
        concepto = str(data["concepto_banco"])[:300]
        existentes = self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.centro_id == centro_id,
            MovimientoBancario.fecha_operacion == fecha,
            MovimientoBancario.importe == importe)).all()
        igual = next((m for m in existentes if self._mismo_concepto(m.concepto_banco, concepto)), None)
        if igual:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Ya existe un apunte igual (id {igual.id}): {fecha} · "
                                f"{igual.concepto_banco[:60]} · {_d(importe)} €.")
        m = MovimientoBancario(
            centro_id=centro_id,
            iban_cuenta=(data.get("iban_cuenta") or "MANUAL")[:34],
            fecha_operacion=fecha,
            concepto_banco=concepto,
            importe=importe,
            categoria=(data.get("categoria") or None))
        self.session.add(m); self.session.commit()
        return {"id": m.id, "tipo": "debe" if m.importe < 0 else "haber"}

    def delete_movimiento(self, centro_id: int, mid: int) -> dict:
        """Borra un apunte (manual o importado). Bloqueado si algo depende de él —una
        factura asociada, un pago de paciente conciliado, o una liquidación de tarjeta que
        lo referencia— porque borrar en cascada un dato financiero sin que el usuario lo
        decida explícitamente es exactamente el tipo de "arreglo" que genera agujeros
        contables. Hay que desasociar primero; el borrado en sí nunca lo hace por su cuenta."""
        m = self._get(MovimientoBancario, mid, centro_id)
        if self.session.exec(select(Gasto).where(Gasto.movimiento_id == mid)).first():
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Este apunte tiene una factura asociada. Desasóciala antes de borrarlo.")
        if m.pago_id:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Este apunte está conciliado con un pago de paciente. Desasócialo antes de borrarlo.")
        if self.session.exec(select(Pago).where(Pago.liquidacion_mov_id == mid)).first():
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Este apunte es una liquidación de tarjeta con pagos conciliados a él. No se puede borrar.")
        snap = {"fecha": str(m.fecha_operacion), "concepto": m.concepto_banco, "importe": _d(m.importe)}
        self.session.delete(m)
        self.session.commit()
        return snap

    @staticmethod
    def _concepto_norm(s: str) -> str:
        """Concepto normalizado (espacios/mayúsculas) para comparar. concepto_banco en sí sigue
        intacto (inmutable, SpecLock) — esto es solo para la comparación de identidad."""
        return " ".join(str(s or "").strip().lower().split())

    @classmethod
    def _mismo_concepto(cls, a: str, b: str) -> bool:
        """IDÉNTICO de verdad — no un corte de longitud fija (eso fusionaría "Alquiler Abril" con
        "Alquiler Mayo" si la palabra que distingue cae justo después del corte: bug real, 2026-08-09).
        Un mismo apunte puede llegar truncado en un punto DISTINTO según la exportación del banco
        ("...Ref. Mandato" vs "...Ref. Mandato Esb859...", visto en producción) — eso SÍ es el mismo
        concepto, porque uno es literalmente el principio exacto del otro (no diverge en nada de lo
        que comparten). "Alquiler Abril" vs "Alquiler Mayo" SÍ divergen antes de que acabe cualquiera
        de los dos → no son iguales, aunque compartan un prefijo largo."""
        na, nb = cls._concepto_norm(a), cls._concepto_norm(b)
        return na == nb or na.startswith(nb) or nb.startswith(na)

    def import_movimientos(self, centro_id: int, rows: list[dict]) -> dict:
        """Importa apuntes de extracto, idempotente ante re-subidas del MISMO fichero.

        Identidad del apunte = centro + iban + fecha + importe + prefijo normalizado del concepto.
        Regla ABSOLUTA (decisión del usuario, 2026-08-09): no puede haber dos apuntes con la misma
        fecha+concepto+importe, de ningún tipo — ni siquiera dentro del mismo fichero subido. El
        saldo posterior NO cuenta para la identidad (era la causa de los duplicados anteriores:
        el mismo movimiento con saldo distinto reportado entre dos exportaciones del banco).
        """
        creados = 0
        nuevos: list[MovimientoBancario] = []
        # Apuntes ya vistos EN ESTE fichero: (iban, fecha, importe, concepto_crudo) — el concepto se
        # compara con _mismo_concepto(), no por igualdad de tupla, así un duplicado DENTRO del propio
        # fichero (mismo caso que entre ficheros) también se detecta.
        vistos_en_fichero: list[tuple] = []
        for r in rows:
            importe = Decimal(str(r["importe"]))
            saldo = Decimal(str(r["saldo_posterior"])) if r.get("saldo_posterior") is not None else None
            concepto_actual = r["concepto_banco"]
            clave_actual = (r["iban_cuenta"], r["fecha_operacion"], importe)
            if any(iban == clave_actual[0] and fecha == clave_actual[1] and imp == clave_actual[2]
                   and self._mismo_concepto(concepto, concepto_actual)
                   for iban, fecha, imp, concepto in vistos_en_fichero):
                continue  # duplicado DENTRO del propio fichero subido
            base = (MovimientoBancario.centro_id == centro_id,
                    MovimientoBancario.iban_cuenta == r["iban_cuenta"],
                    MovimientoBancario.fecha_operacion == r["fecha_operacion"],
                    MovimientoBancario.importe == importe)
            existentes = self.session.exec(select(MovimientoBancario).where(*base)).all()
            vistos_en_fichero.append((*clave_actual, concepto_actual))
            if any(self._mismo_concepto(m.concepto_banco, concepto_actual) for m in existentes):
                continue
            nuevo = MovimientoBancario(
                centro_id=centro_id, iban_cuenta=r["iban_cuenta"], fecha_operacion=r["fecha_operacion"],
                concepto_banco=r["concepto_banco"], importe=importe, saldo_posterior=saldo)
            self.session.add(nuevo)
            nuevos.append(nuevo)
            creados += 1
        self.session.commit()
        # ids de lo recién creado: el motor de conciliación se lanza SOLO sobre esto
        # (no sobre todo el histórico) para que la factura salga al subir el extracto.
        return {"importados": creados, "omitidos": len(rows) - creados,
                "ids": [m.id for m in nuevos if m.id is not None]}

    def importar_movimientos_archivo(self, centro_id: int, contenido: bytes, filename: str = "",
                                     iban_default: str = "") -> dict:
        """Importa un extracto bancario en cualquiera de los formatos comunes (XLSX, XLS, CSV/TXT):
        extrae las filas según el formato y reutiliza el MISMO parser robusto (`_importar_filas`)."""
        try:
            filas = _filas_de_archivo(contenido, filename)
        except ImportError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "El lector de .xls no está disponible aquí. Sube el extracto en XLSX o CSV.")
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        except Exception as e:  # raiz: extracto ilegible o corrupto → 400 claro al cliente
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"No se pudo leer el extracto: {e}")
        if not filas:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El fichero está vacío.")
        return self._importar_filas(centro_id, filas, iban_default)

    def _importar_filas(self, centro_id: int, filas: list, iban_default: str = "") -> dict:
        """Detecta la cabecera ('fecha'+'importe'), mapea columnas y crea los apuntes. Reutilizado
        por todos los formatos. Tolera bancos distintos y números/fechas en formato español."""
        def norm(x) -> str:
            return str(x if x is not None else "").strip().lower()

        # Localizar la fila de cabecera (la que tiene 'fecha' e 'importe'); puede venir
        # precedida de filas de metadatos (titular, saldo, cuenta…).
        cab = next((i for i, f in enumerate(filas[:30])
                    if any("fecha" in norm(c) for c in f)
                    and any("import" in norm(c) for c in f)), None)
        if cab is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "No se encontró la cabecera (se esperan columnas 'fecha' e 'importe').")
        cols = {j: norm(c) for j, c in enumerate(filas[cab])}

        def col(*keys) -> Optional[int]:
            for k in keys:  # prioridad por orden de keys
                for j, c in cols.items():
                    if k in c:
                        return j
            return None

        c_fecha = col("fecha operaci", "fecha contable", "fecha valor", "f. valor", "fecha")
        c_conc = col("concepto", "descrip", "detalle", "observ", "movimiento")
        c_imp = col("importe", "import")
        c_saldo = col("saldo")
        c_iban = col("iban", "cuenta")
        # IBAN: si no hay columna por fila, buscarlo en los metadatos de cabecera.
        if c_iban is None and not iban_default:
            import re as _re
            for f in filas[:cab]:
                for c in f:
                    mm = _re.search(r"\bES\d{2}[\s\d]{18,26}", str(c or ""))
                    if mm:
                        iban_default = mm.group(0).replace(" ", "")[:34]
                        break
                if iban_default:
                    break
        if c_fecha is None or c_imp is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Faltan columnas obligatorias 'fecha' o 'importe'.")

        def to_num(v) -> Optional[Decimal]:
            if v is None or v == "":
                return None
            if isinstance(v, (int, float)):
                return Decimal(str(v))
            s = str(v).replace("€", "").replace(" ", "").strip()
            s = s.replace(".", "").replace(",", ".") if "," in s else s
            try:
                return Decimal(s)
            except Exception:  # raiz: importe ilegible en el CSV → fila descartada
                return None

        def to_fecha(v):
            if isinstance(v, date):
                return v
            if hasattr(v, "date"):
                return v.date()
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
                try:
                    from datetime import datetime
                    return datetime.strptime(str(v).strip(), fmt).date()
                except Exception:  # raiz: formato de fecha no casa → probar el siguiente
                    continue
            return None

        rows, descartadas = [], 0
        for f in filas[cab + 1:]:
            fecha = to_fecha(f[c_fecha]) if c_fecha < len(f) else None
            importe = to_num(f[c_imp]) if c_imp < len(f) else None
            if fecha is None or importe is None:
                descartadas += 1
                continue
            rows.append({
                "iban_cuenta": (str(f[c_iban]).strip() if c_iban is not None and c_iban < len(f) and f[c_iban]
                                else iban_default) or "SIN-IBAN",
                "fecha_operacion": fecha,
                "concepto_banco": (str(f[c_conc]).strip()[:300] if c_conc is not None and c_conc < len(f)
                                   and f[c_conc] else "—"),
                "importe": importe,
                "saldo_posterior": to_num(f[c_saldo]) if c_saldo is not None and c_saldo < len(f) else None,
            })
        res = self.import_movimientos(centro_id, rows)
        res["leidas"] = len(rows)
        res["descartadas"] = descartadas
        return res

    # ───────── PAGOS DE PACIENTES (web) ─────────
    def list_pagos_pacientes(self, centro_id: int, *, anyo: Optional[int] = None,
                             forma: Optional[str] = None) -> dict:
        """Pagos de pacientes (todas las formas), positivos o negativos (devolución), con su
        apunte bancario asociado: Haber para cobros, Debe para devoluciones."""
        from domain.models.core import Paciente
        # Filtro por GRUPO del catálogo único formas_pago (p. ej. "Tarjeta" incluye tarjeta pronto pago).
        from application.services.formas_pago_service import mapa_formas
        catalogo = mapa_formas(self.session)
        usados = set(self.session.exec(select(Pago.forma_pago_id).where(
            Pago.centro_id == centro_id, Pago.anulado == False).distinct()).all())  # noqa: E712
        grupos = {}
        for f in sorted(catalogo.values(), key=lambda x: (x.orden, x.id)):
            if f.id in usados:
                grupos.setdefault(f.grupo, []).append(f.id)
        formas = list(grupos)

        stmt = select(Pago).where(Pago.centro_id == centro_id, Pago.anulado == False)  # noqa: E712
        if anyo:
            stmt = stmt.where(Pago.fecha >= date(anyo, 1, 1), Pago.fecha <= date(anyo, 12, 31))
        if forma:
            stmt = stmt.where(Pago.forma_pago_id.in_(grupos.get(forma) or [-1]))
        rows = self.session.exec(stmt.order_by(Pago.fecha.desc()).limit(1000)).all()
        pacs = {p.id: (p.nombre or "", p.apellidos or "")
                for p in self.session.exec(select(Paciente).where(Paciente.centro_id == centro_id)).all()}
        movs = {m.pago_id: m for m in self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.centro_id == centro_id, MovimientoBancario.pago_id.is_not(None))).all()}
        # Liquidaciones de TPV que cubren pagos con tarjeta (conciliación por lote, no 1:1).
        liq_ids = {p.liquidacion_mov_id for p in rows if p.liquidacion_mov_id}
        liqs = {m.id: m for m in self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.id.in_(liq_ids))).all()} if liq_ids else {}
        data = []
        for p in rows:
            nom, ape = pacs.get(p.paciente_id, ("", ""))
            m = movs.get(p.id)
            lq = liqs.get(p.liquidacion_mov_id)
            data.append({
                "id": p.id, "fecha": str(p.fecha),
                "nombre": nom or None, "apellidos": ape or None,
                "paciente": (f"{nom} {ape}".strip() or "—"),
                "importe": _d(p.importe), "esDevolucion": (p.importe or 0) < 0,
                "formaPago": catalogo[p.forma_pago_id].grupo if p.forma_pago_id in catalogo else None, "numRecibo": p.num_recibo,
                "movimientoId": m.id if m else None,
                "movimientoConcepto": (f"{m.fecha_operacion} · {_d(m.importe)}€" if m else None),
                # Conciliación por liquidación de TPV: qué liquidación abonó este cobro con tarjeta.
                "liquidado": bool(p.liquidado),
                "liquidacionId": p.liquidacion_mov_id,
                "liquidacionConcepto": (f"Liquidación {lq.fecha_operacion} · {_d(lq.importe)}€" if lq else None),
            })
        return {"data": data, "formas": formas}

    def asociar_pago_movimiento(self, centro_id: int, pago_id: int, movimiento_id: int) -> dict:
        p = self._get(Pago, pago_id, centro_id)
        m = self._get(MovimientoBancario, movimiento_id, centro_id)
        # Cobro (importe ≥ 0) → apunte del Haber; devolución (importe < 0) → apunte del Debe.
        if (p.importe or 0) < 0 and m.importe > 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Una devolución se concilia con un apunte del Debe (salida).")
        if (p.importe or 0) >= 0 and m.importe < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Un cobro se concilia con un apunte del Haber (entrada).")
        if m.pago_id and m.pago_id != pago_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ese apunte ya está asociado a otro pago.")
        for otro in self.session.exec(select(MovimientoBancario).where(
                MovimientoBancario.centro_id == centro_id, MovimientoBancario.pago_id == pago_id)).all():
            otro.pago_id = None; otro.estado_concil = "abierto"; self.session.add(otro)
        m.pago_id = pago_id; m.estado_concil = "conciliado"; self.session.add(m)
        self.session.commit()
        return {"ok": True, "pagoId": pago_id, "movimientoId": movimiento_id}

    def desasociar_pago(self, centro_id: int, pago_id: int) -> dict:
        self._get(Pago, pago_id, centro_id)
        for m in self.session.exec(select(MovimientoBancario).where(
                MovimientoBancario.centro_id == centro_id, MovimientoBancario.pago_id == pago_id)).all():
            m.pago_id = None; m.estado_concil = "abierto"; self.session.add(m)
        self.session.commit()
        return {"ok": True}

    def movimientos_haber_libres(self, centro_id: int) -> dict:
        rows = self.session.exec(select(MovimientoBancario).where(
            MovimientoBancario.centro_id == centro_id, MovimientoBancario.importe >= 0,
            MovimientoBancario.pago_id.is_(None)).order_by(MovimientoBancario.fecha_operacion.desc())).all()
        return {"data": [{"id": m.id, "label": f"{m.fecha_operacion} · {m.concepto_banco[:40]} · {_d(m.importe)}€"}
                         for m in rows]}

    # ───────── MODELOS FISCALES ─────────
    def list_modelos(self, centro_id: int, ejercicio: Optional[int] = None) -> dict:
        stmt = select(ModeloFiscal).where(ModeloFiscal.centro_id == centro_id)
        if ejercicio:
            stmt = stmt.where(ModeloFiscal.ejercicio == ejercicio)
        rows = self.session.exec(stmt.order_by(ModeloFiscal.ejercicio.desc(), ModeloFiscal.periodo)).all()
        data = [{"id": m.id, "modelo": m.modelo, "ejercicio": m.ejercicio, "periodo": m.periodo,
                 "estado": m.estado, "fechaLimite": str(m.fecha_limite) if m.fecha_limite else None,
                 "cuota": _d(m.cuota_resultante) if m.cuota_resultante is not None else None} for m in rows]
        pres = sum(1 for m in rows if m.estado == "presentado")
        return {"data": data, "kpis": {"total": len(rows), "presentados": pres, "pendientes": len(rows) - pres}}

    def upsert_modelo(self, centro_id: int, data: dict) -> dict:
        m = self.session.exec(select(ModeloFiscal).where(
            ModeloFiscal.centro_id == centro_id, ModeloFiscal.modelo == data["modelo"],
            ModeloFiscal.ejercicio == data["ejercicio"], ModeloFiscal.periodo == data["periodo"])).first()
        if not m:
            m = ModeloFiscal(centro_id=centro_id, modelo=data["modelo"],
                             ejercicio=data["ejercicio"], periodo=data["periodo"])
        for f in ("estado", "fecha_limite"):
            if f in data:
                setattr(m, f, data[f])
        if data.get("cuota_resultante") is not None:
            m.cuota_resultante = Decimal(str(data["cuota_resultante"]))
        self.session.add(m); self.session.commit()
        return {"id": m.id}

    # Vencimientos estándar AEAT (modelo, periodo, mes/día límite, descripción).
    _VENCIMIENTOS = [
        ("303", "1T", (4, 20), "IVA · 1er trimestre"), ("303", "2T", (7, 20), "IVA · 2º trimestre"),
        ("303", "3T", (10, 20), "IVA · 3er trimestre"), ("303", "4T", (1, 30), "IVA · 4º trimestre"),
        ("130", "1T", (4, 20), "IRPF pago fraccionado · 1T"), ("130", "2T", (7, 20), "IRPF pago fraccionado · 2T"),
        ("130", "3T", (10, 20), "IRPF pago fraccionado · 3T"), ("130", "4T", (1, 30), "IRPF pago fraccionado · 4T"),
        ("111", "1T", (4, 20), "Retenciones IRPF · 1T"), ("111", "2T", (7, 20), "Retenciones IRPF · 2T"),
        ("111", "3T", (10, 20), "Retenciones IRPF · 3T"), ("111", "4T", (1, 20), "Retenciones IRPF · 4T"),
        ("390", "AN", (1, 30), "Resumen anual IVA"), ("190", "AN", (1, 31), "Resumen anual retenciones"),
        ("347", "AN", (2, 28), "Operaciones con terceros (>3.005€)"),
    ]

    def calendario_tributario(self, centro_id: int, ejercicio: int, hoy: date) -> dict:
        """Vencimientos fiscales del ejercicio cruzados con los modelos ya presentados."""
        existentes = {(m.modelo, m.periodo): m for m in self.session.exec(select(ModeloFiscal).where(
            ModeloFiscal.centro_id == centro_id, ModeloFiscal.ejercicio == ejercicio)).all()}
        data = []
        for modelo, periodo, (mes, dia), desc in self._VENCIMIENTOS:
            anyo_limite = ejercicio + 1 if (mes <= 2) else ejercicio
            limite = date(anyo_limite, mes, dia)
            m = existentes.get((modelo, periodo))
            if m and m.estado == "presentado":
                estado = "presentado"
            elif limite < hoy:
                estado = "vencido"
            else:
                estado = "pendiente"
            data.append({"modelo": modelo, "periodo": periodo, "descripcion": desc,
                         "fechaLimite": str(limite), "estado": estado,
                         "cuota": _d(m.cuota_resultante) if m and m.cuota_resultante is not None else None,
                         "id": m.id if m else None})
        return {"data": data}

    def generar_modelo(self, centro_id: int, modelo: str, periodo: str, ejercicio: int) -> dict:
        """Crea/actualiza un modelo en borrador con su cuota. Para el 303 calcula el IVA
        soportado real del trimestre desde los gastos contabilizados."""
        venc = next((v for v in self._VENCIMIENTOS if v[0] == modelo and v[1] == periodo), None)
        if not venc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Modelo/periodo no reconocido.")
        mes, dia = venc[2]
        limite = date(ejercicio + 1 if mes <= 2 else ejercicio, mes, dia)
        cuota = None
        detalle = {}
        if modelo == "303":
            cont = self.contabilizacion(centro_id, ejercicio)
            tri = next((d for d in cont["data"] if d["trimestre"] == f"T{periodo[0]}"), None)
            iva_soportado = round(tri["ivaSoportado"], 2) if tri else 0.0
            # Facturación sanitaria dental → exenta de IVA (art. 20 LIVA): repercutido = 0.
            iva_repercutido = 0.0
            cuota = round(iva_repercutido - iva_soportado, 2)
            detalle = {"ivaRepercutido": iva_repercutido, "ivaSoportado": iva_soportado,
                       "nota": "Repercutido 0 (actividad sanitaria exenta). Revisa la prorrata de deducción."}
        res = self.upsert_modelo(centro_id, {"modelo": modelo, "periodo": periodo, "ejercicio": ejercicio,
                                             "fecha_limite": limite, "estado": "borrador",
                                             "cuota_resultante": cuota})
        return {**res, "cuota": cuota, **detalle}

    # Categorías válidas para el clasificador por IA (la IA elige una, o "Revisar" si no lo sabe).
    CATEGORIAS_IA = ["Laboratorios", "Materiales", "Suministros", "Servicios", "Seguros",
                     "Asesoría", "Impuestos", "Colaboradores", "Financiación", "Alquiler", "Revisar"]

    def clasificar_gastos_ia(self, centro_id: int, *, execute: bool = False, limite_prov: int = 400) -> dict:
        """Clasifica los gastos SIN categoría haciendo que la IA RAZONE sobre el nombre de cada
        proveedor (no reglas mías): devuelve categoría + confianza + nota. Solo aplica lo de
        confianza alta/media; lo dudoso o desconocido lo deja en 'Revisar' para criterio humano.
        Reversible: la categoría previa está respaldada. execute=False previsualiza.
        Respeta Config→IA's→Gestor (`gestor.config`): activa, capacidades.clasificar_gastos,
        límites.importe_auto_max (gasto por encima → no se aplica solo, queda pendiente de
        confirmación) y límites.max_facturas_dia (tope diario de aplicaciones, contado sobre el
        propio log de auditoría `gestoria.gasto.clasificar_ia`)."""
        import json
        import re as _re
        from datetime import datetime as _dt, time as _time
        from sqlalchemy import func as _f, text as _text
        from application.services.config_service import ConfigService
        from application.services.llm_config import GESTORIA_GASTOS, resolver_llm
        from infrastructure.external_apis.llm_client import LLMClient, LLMError

        gcfg = ConfigService(self.session).resolve("gestor.config", centro_id=centro_id, sistema="gestor", default=None) or {}
        if gcfg and not gcfg.get("activa", True):
            return {"ok": False, "error": "Gestor IA está desactivado en Config → IA's → Gestor."}
        capacidades = gcfg.get("capacidades") or {}
        if not capacidades.get("clasificar_gastos", True):
            return {"ok": False, "error": "La capacidad 'Clasificar gastos' está desactivada en Config → IA's → Gestor."}
        limites = gcfg.get("limites") or {}
        importe_auto_max = limites.get("importe_auto_max")
        importe_auto_max = float(importe_auto_max) if importe_auto_max is not None else None
        max_facturas_dia = int(limites.get("max_facturas_dia") or 0) or None
        cupo_restante = None
        if execute and max_facturas_dia is not None:
            inicio_dia = _dt.combine(_dt.utcnow().date(), _time.min)
            aplicadas_hoy = self.session.exec(_text(
                "SELECT COALESCE(SUM((detalle->>'aplicados')::int), 0) FROM auditoria "
                "WHERE accion='gestoria.gasto.clasificar_ia' AND centro_id=:c AND created_at >= :inicio"
            ).bindparams(c=centro_id, inicio=inicio_dia)).one()[0]
            cupo_restante = max(0, max_facturas_dia - int(aplicadas_hoy or 0))
            if cupo_restante == 0:
                return {"ok": False, "error": f"Tope diario de Gestor alcanzado ({max_facturas_dia} facturas/día, Config → IA's → Gestor → Límites)."}

        llm_cfg = resolver_llm(self.session, centro_id, GESTORIA_GASTOS)
        if not llm_cfg:
            return {"ok": False, "error": "Gestor IA no está configurado (falta el motor LLM)."}

        rows = self.session.exec(select(Gasto.proveedor_extraido, _f.sum(Gasto.total)).where(
            Gasto.centro_id == centro_id, (Gasto.categoria.is_(None)) | (Gasto.categoria == "")
        ).group_by(Gasto.proveedor_extraido)).all()
        # (raw en BD, nombre a mostrar, importe) — el nombre a mostrar es lo que ve/razona la IA.
        provs = [(raw, (raw or "").strip() or "(sin nombre)", float(t or 0)) for raw, t in rows]
        provs = sorted(provs, key=lambda x: -x[2])[:limite_prov]

        sistema = (
            "Eres analista contable de una CLÍNICA DENTAL en España. Clasifica cada PROVEEDOR en UNA "
            "categoría a partir de su nombre, usando tu conocimiento del sector dental español. Categorías: "
            + ", ".join(self.CATEGORIAS_IA) + ". Reglas: 'Colaboradores' = doctor/persona física; "
            "'Laboratorios' = prótesis/fresado/CAD-CAM; 'Materiales' = implantes/consumibles/casas dentales; "
            "'Suministros' = luz/agua/teléfono; 'Financiación' = bancos/financieras/leasing; "
            "'Revisar' SOLO si el nombre es ilegible, es la PROPIA clínica, o no puedes saberlo con criterio. "
            "Devuelve EXCLUSIVAMENTE un array JSON: "
            '[{"proveedor":"<tal cual>","categoria":"<una>","confianza":"alta|media|baja","nota":"<=6 palabras"}]')

        clasif: dict[str, dict] = {}
        CHUNK = 30
        for i in range(0, len(provs), CHUNK):
            lote = provs[i:i + CHUNK]
            lista = "\n".join(f"- {disp} ({t:,.0f} €)" for _raw, disp, t in lote)
            try:
                msg = LLMClient(llm_cfg).chat(
                    [{"role": "system", "content": sistema}, {"role": "user", "content": lista}],
                    temperature=0.1, max_tokens=1500)
                m = _re.search(r"\[.*\]", msg.get("content") or "", _re.S)
                for d in (json.loads(m.group(0)) if m else []):
                    cat = d.get("categoria")
                    if isinstance(d.get("proveedor"), str) and cat in self.CATEGORIAS_IA:
                        clasif[d["proveedor"].strip()] = {"categoria": cat,
                                                          "confianza": d.get("confianza", "baja"),
                                                          "nota": (d.get("nota") or "")[:60]}
            except (LLMError, ValueError):
                continue

        res = {"ok": True, "execute": execute, "proveedores": len(provs), "respondidos": len(clasif),
               "aplicados": 0, "revisar": 0, "pendientesConfirmacion": 0, "porCategoria": {}, "muestra": []}
        aplicar = {p: c for p, c in clasif.items()
                   if c["categoria"] != "Revisar" and c["confianza"] in ("alta", "media")}
        res["revisar"] = sum(1 for c in clasif.values() if c["categoria"] == "Revisar" or c["confianza"] == "baja")
        for p, c in list(clasif.items())[:25]:
            res["muestra"].append({"proveedor": p, **c})
        if aplicar:
            tope_alcanzado = False
            for raw, disp, _t in provs:
                if tope_alcanzado:
                    break
                c = aplicar.get(disp)
                if not c:
                    continue
                cond = Gasto.proveedor_extraido.is_(None) if raw is None else (Gasto.proveedor_extraido == raw)
                gastos = self.session.exec(select(Gasto).where(
                    Gasto.centro_id == centro_id, (Gasto.categoria.is_(None)) | (Gasto.categoria == ""), cond)).all()
                for g in gastos:
                    importe = float(g.total or 0)
                    # Config→Límites→"Automatización hasta X €": por encima, queda pendiente de
                    # confirmación aunque la IA tenga confianza alta.
                    if importe_auto_max is not None and importe > importe_auto_max:
                        res["pendientesConfirmacion"] += 1
                        continue
                    if cupo_restante is not None:
                        if cupo_restante <= 0:
                            tope_alcanzado = True
                            break
                        cupo_restante -= 1
                    res["porCategoria"][c["categoria"]] = res["porCategoria"].get(c["categoria"], 0) + 1
                    res["aplicados"] += 1
                    if execute:
                        g.categoria = c["categoria"]; self.session.add(g)
            if execute:
                self.session.commit()
        return res

    # ───────── ENVÍO A GESTORÍA ─────────
    # Secciones que se pueden mandar; por defecto van las que ve la asesoría en su acceso
    # restringido: Facturas (gastos) + Debe/Haber (bancos). Decisión del usuario (8-jul-2026).
    ENVIO_TABLAS = ["facturas", "gastos", "bancos", "modelos", "produccion"]

    def _envio_auto_cfg(self, centro_id: int) -> dict:
        """Config del envío automático (clave `gestoria.envio_auto`). Por defecto: apagado, día 15."""
        cfg = self.session.exec(select(Configuracion).where(
            Configuracion.centro_id == centro_id, Configuracion.clave == "gestoria.envio_auto",
            Configuracion.sistema.is_(None), Configuracion.usuario_id.is_(None))).first()
        v = (cfg.valor or {}) if cfg else {}
        return {"activo": bool(v.get("activo")), "dia": int(v.get("dia") or 15),
                "tablas": v.get("tablas") or ["gastos", "bancos"], "ultimoEnvio": v.get("ultimoEnvio")}

    def config_envio(self, centro_id: int) -> dict:
        cfg = self.session.exec(select(Configuracion).where(
            Configuracion.centro_id == centro_id, Configuracion.clave == "gestoria.asesoria")).first()
        ase = (cfg.valor or {}) if cfg else {}
        ig = self._smtp(centro_id)
        return {"destino": ase.get("email"), "nombreAsesoria": ase.get("nombre") or ase.get("contacto"),
                "remitente": (ig.config or {}).get("direccion") if ig else None,
                "smtpListo": bool(ig and (ig.config or {}).get("password")),
                "auto": self._envio_auto_cfg(centro_id)}

    def set_envio_auto(self, centro_id: int, *, activo: bool, dia: int, tablas: list[str]) -> dict:
        """Programa (o apaga) el envío automático mensual a la asesoría. Preserva `ultimoEnvio`."""
        from application.services.config_service import ConfigService
        dia = max(1, min(28, int(dia)))   # 1–28 para que exista en todos los meses
        prev = self._envio_auto_cfg(centro_id)
        ConfigService(self.session).set("gestoria.envio_auto", {
            "activo": bool(activo), "dia": dia,
            "tablas": [t for t in (tablas or []) if t in self.ENVIO_TABLAS] or ["gastos", "bancos"],
            "ultimoEnvio": prev.get("ultimoEnvio"),
        }, centro_id=centro_id)
        return self._envio_auto_cfg(centro_id)

    def enviar_programado(self, centro_id: int, hoy: date) -> Optional[dict]:
        """Lo llama el scheduler a diario. Si toca (día del mes y no enviado ya este mes), manda a la
        asesoría los datos del año en curso y anota el mes para no duplicar. Idempotente."""
        c = self._envio_auto_cfg(centro_id)
        marca = f"{hoy.year}-{hoy.month:02d}"
        # Se manda el primer día ≥ programado que aún no se haya enviado este mes (así, si el día 15
        # el servidor estaba caído o el SMTP falló, se recupera el 16, 17… en vez de esperar un mes).
        if not c["activo"] or hoy.day < c["dia"] or c.get("ultimoEnvio") == marca:
            return None
        ase = self.session.exec(select(Configuracion).where(
            Configuracion.centro_id == centro_id, Configuracion.clave == "gestoria.asesoria")).first()
        destino = (ase.valor or {}).get("email") if ase else None
        res = self.enviar_gestoria(centro_id, tablas=c["tablas"], anyo=hoy.year, destino=destino)
        if res.get("ok"):   # solo marcamos el mes si el correo salió (si falla, reintenta mañana)
            from application.services.config_service import ConfigService
            ConfigService(self.session).set("gestoria.envio_auto", {**c, "ultimoEnvio": marca}, centro_id=centro_id)
        return res

    def _smtp(self, centro_id: int):
        return self.session.exec(select(Integracion).where(
            Integracion.centro_id == centro_id, Integracion.tipo == "email_saliente")).first()

    # Etiqueta legible de cada sección (para el nombre del CSV y el cuerpo del correo).
    _SECCION_LABEL = {"facturas": "Facturas emitidas", "gastos": "Gastos", "bancos": "Movimientos bancarios",
                      "modelos": "Modelos fiscales", "produccion": "Producción doctores"}

    @staticmethod
    def _csv_de(rows: list[dict]) -> Optional[bytes]:
        """CSV (delimitador ';' + BOM, para que Excel-ES respete acentos y columnas) desde filas dict.
        Cabeceras = unión de claves. Devuelve None si no hay filas."""
        if not rows:
            return None
        cols: list[str] = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])
        return ("﻿" + buf.getvalue()).encode("utf-8")

    def _datos_seccion(self, centro_id: int, tabla: str, anyo: int) -> list[dict]:
        """Filas de una sección para el año `anyo` (para adjuntar como CSV). [] si falla."""
        ini, fin = date(anyo, 1, 1), date(anyo, 12, 31)
        try:
            if tabla == "facturas":
                return self.facturas_emitidas(centro_id, anyo=anyo)["data"]
            if tabla == "gastos":
                return self.list_gastos(centro_id, desde=ini, hasta=fin)["data"]
            if tabla == "bancos":
                return self.list_movimientos(centro_id, anyo=anyo)["data"]
            if tabla == "modelos":
                return self.list_modelos(centro_id, ejercicio=anyo)["data"]
            if tabla == "produccion":
                from application.services.produccion_service import ProduccionService
                return ProduccionService(self.session).doctores(centro_id, ini, fin)["data"]
        except Exception:  # raiz: una sección que falle no debe tumbar el envío
            return []
        return []

    def enviar_gestoria(self, centro_id: int, *, tablas: list[str], anyo: int,
                        destino: Optional[str]) -> dict:
        ig = self._smtp(centro_id)
        if not ig or not (ig.config or {}).get("password"):
            return {"ok": False, "error": "SMTP no configurado"}
        destino = (destino or "").strip()   # el email de la config puede traer espacios
        if not destino:
            return {"ok": False, "error": "Falta el email de la asesoría"}
        d = self.dashboard(centro_id, date(anyo, 1, 1), date(anyo, 12, 31))
        # Un CSV por sección marcada; solo se adjunta si tiene filas.
        adjuntos, lineas = [], []
        for t in tablas:
            csv_bytes = self._csv_de(self._datos_seccion(centro_id, t, anyo))
            label = self._SECCION_LABEL.get(t, t)
            n = 0 if csv_bytes is None else max(0, csv_bytes.count(b"\n") - 1)
            if csv_bytes:
                adjuntos.append({"filename": f"{t}_{anyo}.csv", "content": csv_bytes, "mimetype": "text/csv"})
            lineas.append(f"<li>{label}: {n} registro(s){' (adjunto)' if csv_bytes else ' — sin datos'}</li>")
        html = (f"<h2 style='color:#065AED'>Gestoría {anyo}</h2>"
                f"<p>Resumen del ejercicio:</p>"
                f"<ul><li>Ingresos: {d['ingresos']:.2f} €</li><li>Gastos: {d['gastos']:.2f} €</li>"
                f"<li>Balance: {d['balance']:.2f} €</li><li>Facturas emitidas: {d['facturasEmitidas']}</li></ul>"
                f"<p>Secciones adjuntas (CSV):</p><ul>{''.join(lineas) or '<li>—</li>'}</ul>")
        return smtp_mailer.send_html(ig.config, to=destino, subject=f"Datos gestoría {anyo}",
                                     html=html, attachments=adjuntos)

    # ───────── helpers ─────────
    def _get(self, model, oid: int, centro_id: int):
        obj = self.session.get(model, oid)
        if not obj or obj.centro_id != centro_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} no encontrado")
        return obj
