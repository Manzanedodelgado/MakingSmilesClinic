"""Tests del motor de conciliación banco↔factura y de las plantillas PDF.

Cubre lo que antes se comprobaba a mano: clasificación de apuntes, numeración de Melero,
generación de recurrentes (alquiler/parking/colaborador), contabilización de impuestos, dry-run.
Corre sobre SQLite (fixture `session`); la generación de PDF usa fitz real y NO sube a Drive
(sin integración google_drive → el gasto se crea sin archivo_pdf_url).
"""
from datetime import date
from decimal import Decimal

from sqlmodel import select

from application.services import documento_pdf as pdfdoc
from application.services.conciliacion_service import ConciliacionService, _iniciales, _num_contrato_melero
from domain.models.core import Colaborador
from domain.models.gestoria import Gasto, MovimientoBancario
from domain.models.identidad import Usuario, UsuarioPeriodo


def _mov(session, concepto, importe, f=date(2025, 6, 15)):
    m = MovimientoBancario(centro_id=1, iban_cuenta="ES0000000000000000000000", fecha_operacion=f,
                           concepto_banco=concepto, importe=Decimal(str(importe)), estado_concil="abierto")
    session.add(m); session.commit(); session.refresh(m)
    return m


# ───────────────────────── plantillas PDF ─────────────────────────
def test_plantillas_pdf_devuelven_pdf_valido():
    a = pdfdoc.recibo_alquiler("21/60", "01-04-2026", 3183.0, "Aureliano Melero", "Mayor 19", "289.369-Y")
    b = pdfdoc.autofactura("IGS202406", "10-06-2024", "Irene García", "47541434C", "28011085", 1458.82, 0.15, "Servicios")
    c = pdfdoc.factura_generica("GAR202506", "01-06-2025", "Garaje SL", None, "Plaza garaje", 75.0, 0.21)
    for pdf in (a, b, c):
        assert pdf[:5] == b"%PDF-" and len(pdf) > 800


def test_eur_formato_espanol():
    assert pdfdoc.eur(1458.82) == "1.458,82 €"
    assert pdfdoc.eur(75) == "75,00 €"


# ───────────────────────── helpers ─────────────────────────
def test_iniciales():
    assert _iniciales("Juan Antonio", "Manzanedo Delgado") == "JMD"
    assert _iniciales("Virginia", "Tresgallo de la Peña") == "VTP"   # 'de la' se ignoran
    assert _iniciales("Irene", "García Sanz") == "IGS"


def test_num_contrato_melero():
    assert _num_contrato_melero(2024, 8) == "01/60"    # contrato 2 arranca ago-2024
    assert _num_contrato_melero(2026, 4) == "21/60"    # recibo real que dio el usuario
    assert _num_contrato_melero(2019, 8) == "01/60"    # contrato 1 arranca ago-2019


# ───────────────────────── clasificación ─────────────────────────
def test_clasifica_tipos(session):
    svc = ConciliacionService(session, 1)
    assert svc._tipo("Transferencia A Favor De Aureliano Melero") == "alquiler"
    assert svc._tipo("Recibo Estacionamientos Y Garajes Virgen Bl") == "parking"
    # IS y pagos a cuenta → gasto
    assert svc._tipo("Domiciliacion Impuesto: 2024 Imp. Sociedades Pago A Cta") == "impuesto"
    # Retención IRPF (mod. 115) → se refleja como retención, NO como impuesto/gasto propio
    assert svc._tipo("Domiciliacion Impuesto: Irpf. E Is. Ret. Inm. Urbanos") == "retencion"
    assert svc._tipo("Retenciones E Ing. A Cta. Ggee.") == "retencion"
    # IVA → neutro, no es gasto → revisión
    assert svc._tipo("Liquidacion IVA modelo 303") == "iva"
    # préstamo → solo interés → revisión
    assert svc._tipo("Liquidacion Periodica Prestamo") == "prestamo"
    assert svc._tipo("Recibo Tgss. Cotizacion Regimen General") == "ss"
    assert svc._tipo("Recibo Zurich Seguros") == "seguro"
    assert svc._tipo("Recibo Proclinic S.A.") is None   # no recurrente → revisión


def _factura_de(session, m):
    """Factura enlazada a un apunte. El vínculo vive en Gasto.movimiento_id (migración 025)."""
    return session.exec(select(Gasto).where(Gasto.movimiento_id == m.id)).first()


# ───────────────────────── generación ─────────────────────────
def test_genera_alquiler(session):
    m = _mov(session, "Transferencia Inmediata A Favor De Aureliano Melero", -3246.66, date(2026, 4, 30))
    r = ConciliacionService(session, 1).cuadrar(execute=True)
    assert r["generadas"]["alquiler"] == 1
    session.refresh(m)
    g = _factura_de(session, m)
    assert g is not None and g.numero_factura == "21/60" and g.categoria == "Alquiler"
    assert g.cif_emisor == "00289369Y" and float(g.total) == 3246.66
    assert abs(float(g.base_imponible) - 3183.0) < 0.5   # base = total/1.02


def test_genera_parking(session):
    m = _mov(session, "Recibo Estacionamientos Y Garajes Virgen Bl", -75.00, date(2025, 6, 1))
    ConciliacionService(session, 1).cuadrar(execute=True)
    session.refresh(m)
    g = _factura_de(session, m)
    assert g.numero_factura == "GAR202506" and g.categoria == "Alquiler" and float(g.total) == 75.0


def test_bnp_renting_impresora_cuota_completa(session):
    # BNP Paribas Lease = renting de la impresora → cuota COMPLETA es gasto, NO va a la bandeja de interés.
    m = _mov(session, "Recibo Bnp Paribas Lease Group S.a Sucursal En Renting Nº Recibo 0049", -45.70, date(2025, 6, 5))
    svc = ConciliacionService(session, 1)
    assert svc._tipo(m.concepto_banco) == "renting"
    r = svc.cuadrar(execute=True)
    assert r["generadas"]["renting"] == 1 and r["requiere_datos"] == 0
    session.refresh(m)
    g = _factura_de(session, m)
    assert g.categoria == "Renting" and g.numero_factura == "BNP202506" and float(g.total) == 45.70
    assert m.estado_concil == "conciliado"


def test_contabiliza_impuesto(session):
    m = _mov(session, "Domiciliacion Impuesto: Impuesto Sociedades", -805.00)
    r = ConciliacionService(session, 1).cuadrar(execute=True)
    assert r["contabilizadas"]["impuesto"] == 1
    session.refresh(m)
    g = _factura_de(session, m)
    assert g.categoria == "Impuestos" and g.numero_factura is None and float(g.total) == 805.0


def test_retencion_irpf_se_refleja_no_como_impuesto(session):
    m = _mov(session, "Domiciliacion Impuesto: 2025 Irpf. E Is. Ret. Inm. Urbanos", -1814.31)
    r = ConciliacionService(session, 1).cuadrar(execute=True)
    assert r["contabilizadas"]["retencion"] == 1 and r["contabilizadas"]["impuesto"] == 0
    session.refresh(m)
    assert _factura_de(session, m).categoria == "Retenciones IRPF"


def test_iva_no_se_contabiliza(session):
    m = _mov(session, "Liquidacion IVA modelo 303", -1200.00)
    r = ConciliacionService(session, 1).cuadrar(execute=True)
    assert r["revision"] == 1 and sum(r["contabilizadas"].values()) == 0
    session.refresh(m)
    assert _factura_de(session, m) is None   # IVA no genera gasto


def test_prestamo_pide_dato_no_se_contabiliza(session):
    m = _mov(session, "Liquidacion Periodica Prestamo", -610.50)
    r = ConciliacionService(session, 1).cuadrar(execute=True)
    assert r["requiere_datos"] == 1 and r["revision"] == 0
    session.refresh(m)
    assert _factura_de(session, m) is None                       # solo el interés sería gasto → no se auto-contabiliza
    assert m.estado_concil == "requiere_datos"      # queda en la bandeja esperando el interés


def test_bandeja_revision_lista_prestamos(session):
    _mov(session, "Liquidacion Periodica Prestamo", -610.50, date(2025, 3, 10))
    svc = ConciliacionService(session, 1)
    svc.cuadrar(execute=True)
    pend = svc.pendientes_revision()["data"]
    assert len(pend) == 1 and pend[0]["pide"] == "interes" and pend[0]["importe"] == 610.50


def test_resolver_prestamo_contabiliza_solo_interes(session):
    m = _mov(session, "Recibo Leasing Vehiculo", -610.50, date(2025, 3, 10))
    svc = ConciliacionService(session, 1)
    svc.cuadrar(execute=True)
    r = svc.resolver_prestamo(m.id, 45.50)
    assert r["interes"] == 45.50 and r["principal"] == 565.0
    session.refresh(m)
    g = _factura_de(session, m)
    assert g.categoria == "Gastos financieros" and float(g.total) == 45.50   # KPI suma total → solo el interés
    assert m.estado_concil == "conciliado"


def test_resolver_prestamo_rechaza_interes_mayor_que_recibo(session):
    m = _mov(session, "Recibo Leasing Vehiculo", -100.0, date(2025, 3, 10))
    svc = ConciliacionService(session, 1)
    svc.cuadrar(execute=True)
    try:
        svc.resolver_prestamo(m.id, 150.0)
        assert False, "debía rechazar interés > importe"
    except ValueError:
        pass


def test_autofactura_colaborador(session):
    u = Usuario(nombre="Daniela", apellidos="Perez Gomez", nif="00000000T")
    session.add(u); session.commit(); session.refresh(u)
    up = UsuarioPeriodo(usuario_id=u.id, centro_id=1, orden=0); session.add(up); session.commit(); session.refresh(up)
    session.add(Colaborador(centro_id=1, periodo_id=up.id, aplica_irpf=False, num_colegiado="123")); session.commit()
    m = _mov(session, "Transferencia A Favor De Daniela Perez Concepto: Id", -500.00, date(2025, 5, 10))
    r = ConciliacionService(session, 1).cuadrar(execute=True)
    assert r["generadas"]["colaborador"] == 1
    session.refresh(m)
    g = _factura_de(session, m)
    assert g.numero_factura == "DPG202505" and g.categoria == "Colaboradores" and float(g.total) == 500.0


# ───────────────────────── tarjeta ↔ liquidación TPV ─────────────────────────
def _liq(session, importe, lote_ddmmaaaa, f):
    m = MovimientoBancario(centro_id=1, iban_cuenta="ES0000000000000000000000", fecha_operacion=f,
                           concepto_banco=f"Liquidacion Efectuada El {lote_ddmmaaaa} A Tridental Odontologos",
                           importe=Decimal(str(importe)), estado_concil="abierto")
    session.add(m); session.commit(); session.refresh(m)
    return m


def _pago_tarjeta(session, importe, f):
    from domain.models.economico import Pago
    p = Pago(centro_id=1, fecha=f, importe=Decimal(str(importe)), forma_pago_id=6)
    session.add(p); session.commit(); session.refresh(p)
    return p


def test_conciliar_tarjeta_casa_lote_con_comision(session):
    # Liquidación de 100 € (lote 15/06) = 2 pagos de tarjeta del día 15 (100,30) − 0,30 de comisión.
    m = _liq(session, 100.00, "15/06/2025", date(2025, 6, 16))
    p1 = _pago_tarjeta(session, 60.30, date(2025, 6, 15))
    p2 = _pago_tarjeta(session, 40.00, date(2025, 6, 15))
    r = ConciliacionService(session, 1).conciliar_tarjetas(execute=True)
    assert r["conciliadas"] == 1 and r["pagos_marcados"] == 2 and abs(r["comision_total"] - 0.30) < 0.01
    session.refresh(m); session.refresh(p1); session.refresh(p2)
    assert m.estado_concil == "conciliado"
    assert p1.liquidado and p1.liquidacion_mov_id == m.id and p2.liquidado


def test_conciliar_tarjeta_marca_hueco_sin_pagos(session):
    # Liquidación de 500 € sin ningún pago con tarjeta que la respalde → hueco 'faltan pagos'.
    m = _liq(session, 500.00, "10/12/2025", date(2025, 12, 11))
    r = ConciliacionService(session, 1).conciliar_tarjetas(execute=True)
    assert len(r["huecos"]) == 1 and r["huecos"][0]["falta"] == 500.0
    session.refresh(m)
    assert m.estado_concil == "falta_pagos" and m.categoria == "Liquidación TPV (faltan pagos)"


# ───────────────────────── dry-run ─────────────────────────
def test_dry_run_no_escribe(session):
    m = _mov(session, "Transferencia A Favor De Aureliano Melero", -3246.66)
    antes = len(session.exec(select(Gasto).where(Gasto.centro_id == 1)).all())
    r = ConciliacionService(session, 1).cuadrar(execute=False)
    assert r["generadas"]["alquiler"] == 1                       # lo previsualiza
    despues = len(session.exec(select(Gasto).where(Gasto.centro_id == 1)).all())
    assert antes == despues                                      # pero NO crea nada
    session.refresh(m)
    assert _factura_de(session, m) is None                                    # ni enlaza


# ───────────────────────── propuesta de eliminar facturas sin Debe ─────────────────────────
def _fac(session, f, total, forma, cat=None, mov=None):
    g = Gasto(centro_id=1, fecha=f, total=Decimal(str(total)), forma_pago=forma, categoria=cat,
              movimiento_id=mov, proveedor_extraido="X", numero_factura=f"N{f}{total}")
    session.add(g); session.commit(); session.refresh(g)
    return g


def test_propuesta_eliminar_solo_meses_cerrados_y_sin_debe(session):
    m = _mov(session, "RECIBO X", -100, f=date(2025, 6, 10))
    _mov(session, "RECIBO Y", -50, f=date(2025, 7, 5))                        # último apunte: julio
    ligada = _fac(session, date(2025, 6, 10), 100, "Transferencia", mov=m.id)  # tiene Debe → no
    sobra = _fac(session, date(2025, 6, 11), 80, "Transferencia")              # sin Debe, mes cerrado → sí
    efectivo = _fac(session, date(2025, 6, 12), 20, "Metálico")                # efectivo = es el Debe → no
    compra = _fac(session, date(2025, 6, 13), 9, "Tarjeta Deb. Juan A. Manzanedo", cat="Software")  # → no
    honor = _fac(session, date(2025, 6, 14), 2000, "Tarjeta Deb. Juan A. Manzanedo", cat="Colaboradores")  # → sí
    abierto = _fac(session, date(2025, 7, 20), 70, "Transferencia")            # mes en curso → no
    r = ConciliacionService(session, 1).facturas_sin_debe()
    assert {d["id"] for d in r["data"]} == {sobra.id, honor.id}
    assert r["mes_cerrado_hasta"] == "2025-06-30" and r["importe"] == 2080.0
    assert not {ligada.id, efectivo.id, compra.id, abierto.id} & {d["id"] for d in r["data"]}
