"""Cuenta económica del paciente: pago a un tratamiento, a un presupuesto aceptado o a cuenta.

Reglas (usuario, 17-oct-2026):
  · Pago a un TRATAMIENTO: puede ser parcial, nunca superar su coste.
  · Pago a un PRESUPUESTO aceptado: se descuenta de los tratamientos de ESE presupuesto según se
    realizan; no paga tratamientos de otro presupuesto.
  · Pago A CUENTA: de él se descuenta cualquier tratamiento realizado.
"""
import os
from datetime import date
from decimal import Decimal

import pytest

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from domain.models.core import Colaborador, Paciente, Tratamiento
from domain.models.economico import Pago, Presupuesto, PresupuestoLinea, TratamientoRealizado
from domain.models.gestoria import Deuda, DeudaPago
from domain.models.identidad import UsuarioPeriodo


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _pac(session: Session) -> Paciente:
    p = Paciente(centro_id=1, nombre="Cuenta", apellidos="Económica")
    session.add(p); session.commit(); session.refresh(p)
    return p


def _tto(session: Session, nombre: str = "Obturación") -> Tratamiento:
    t = Tratamiento(centro_id=1, nombre=nombre, codigo=f"CE{nombre[:3]}", activo=True)
    session.add(t); session.commit(); session.refresh(t)
    return t


def _presupuesto(session: Session, pac: Paciente, estado: int = 3) -> tuple[Presupuesto, PresupuestoLinea]:
    pr = Presupuesto(centro_id=1, paciente_id=pac.id, fecha=date.today(), estado_id=estado, titulo="Implantes")
    session.add(pr); session.commit(); session.refresh(pr)
    t = _tto(session, f"Implante{pr.id}")
    ln = PresupuestoLinea(presupuesto_id=pr.id, tratamiento_id=t.id, precio_unitario=Decimal("300"), cantidad=1)
    session.add(ln); session.commit(); session.refresh(ln)
    return pr, ln


def _acto(session: Session, pac: Paciente, importe: str, linea: PresupuestoLinea | None = None,
          fecha: date | None = None) -> TratamientoRealizado:
    t = _tto(session, f"T{importe}")
    a = TratamientoRealizado(centro_id=1, paciente_id=pac.id, tratamiento_id=t.id, importe=Decimal(importe),
                             estado_id=5, fecha_inicio=fecha or date.today(),
                             presupuesto_linea_id=linea.id if linea else None)
    session.add(a); session.commit(); session.refresh(a)
    return a


def _cobro(client, token, pac, **kw):
    body = {"forma_pago_id": 2, "aplicaciones": []}
    body.update(kw)
    return client.post(f"/inicio/paciente/{pac.id}/cobro", headers=_h(token), json=body)


def _cargo(session: Session, acto: TratamientoRealizado) -> Deuda:
    d = session.exec(select(Deuda).where(Deuda.tratamiento_realizado_id == acto.id)).one()
    session.refresh(d)
    return d


# ── 3. A CUENTA ───────────────────────────────────────────────────────────────────────────
def test_pago_a_cuenta_sin_tratamientos_queda_de_saldo(client: TestClient, token: str, session: Session):
    pac = _pac(session)
    r = _cobro(client, token, pac, importe=200)
    assert r.status_code == 201, r.text
    assert r.json()["saldo"] == 200.0
    pago = session.get(Pago, r.json()["pago_id"])
    assert pago.presupuesto_id is None and pago.importe == Decimal("200.00")
    assert session.exec(select(DeudaPago).where(DeudaPago.pago_id == pago.id)).all() == []


def test_a_cuenta_descuenta_lo_ya_realizado(client: TestClient, token: str, session: Session):
    pac = _pac(session)
    a1 = _acto(session, pac, "80.00", fecha=date(2026, 1, 10))
    a2 = _acto(session, pac, "150.00", fecha=date(2026, 2, 10))
    r = _cobro(client, token, pac, importe=100)
    assert r.status_code == 201, r.text
    assert r.json()["saldo"] == 0.0
    d1, d2 = _cargo(session, a1), _cargo(session, a2)
    assert d1.liquidada and d1.importe_pendiente == Decimal("0.00")          # el más antiguo, entero
    assert d2.importe_pendiente == Decimal("130.00") and not d2.liquidada    # del segundo, el resto (20)


def test_a_cuenta_descuenta_lo_que_se_realiza_despues(client: TestClient, token: str, session: Session):
    pac = _pac(session); t = _tto(session, "Endodoncia")
    assert _cobro(client, token, pac, importe=500).status_code == 201
    r = client.post(f"/pacientes/{pac.id}/actos", headers=_h(token),
                    json={"tratamiento_id": t.id, "fecha": date.today().isoformat(),
                          "importe": 180, "colaborador_id": 1})
    assert r.status_code == 201, r.text
    acto = session.get(TratamientoRealizado, r.json()["id"])
    d = _cargo(session, acto)
    assert d.liquidada and d.importe_pendiente == Decimal("0.00")
    plan = client.get(f"/pacientes/{pac.id}/plan", headers=_h(token)).json()
    assert plan["totales"]["saldo_a_favor"] == 320.0


def test_plan_separa_saldo_historico_del_nuevo_y_cuadra_el_neto(client: TestClient, token: str, session: Session):
    pac = _pac(session)
    t = _tto(session, "Tratamiento histórico")
    acto = TratamientoRealizado(centro_id=1, paciente_id=pac.id, tratamiento_id=t.id,
                                fecha_inicio=date(2019, 1, 1), importe=Decimal("200.00"),
                                descuento=Decimal("20.00"), estado_id=5, origen="GELITE:TtosMed")
    historico = Pago(centro_id=1, paciente_id=pac.id, fecha=date(2019, 2, 1),
                     importe=Decimal("80.00"), forma_pago_id=2, origen="GELITE:PagoCli")
    nuevo = Pago(centro_id=1, paciente_id=pac.id, fecha=date.today(),
                 importe=Decimal("30.00"), forma_pago_id=2)
    ajuste = Pago(centro_id=1, paciente_id=pac.id, fecha=date(2020, 5, 1),
                  importe=Decimal("10.00"), forma_pago_id=18,
                  origen="AJUSTE:anulacion_deuda_pre_mayo2020")
    session.add_all([acto, historico, nuevo, ajuste]); session.commit()

    r = client.get(f"/pacientes/{pac.id}/plan", headers=_h(token))
    assert r.status_code == 200, r.text
    tot = r.json()["totales"]
    assert tot["saldo_historico"] == 90.0        # 200 - 20 descuento - 80 pagados - 10 ajuste
    assert tot["saldo_a_favor"] == 30.0          # solo el pago creado en la app
    assert tot["saldo_total"] == 60.0            # no duplica el saldo histórico
    pagos = {p["id"]: p for p in r.json()["pagos"]}
    assert pagos[ajuste.id]["asociado_a"] == "Ajuste contable"


def test_liberar_pago_aplica_saldo_a_deuda_abierta_y_deja_el_sobrante(
    client: TestClient, token: str, session: Session
):
    pac = _pac(session)
    presupuesto, _ = _presupuesto(session, pac)
    cobro = _cobro(client, token, pac, importe=100, presupuesto_id=presupuesto.id)
    assert cobro.status_code == 201, cobro.text
    pago = session.get(Pago, cobro.json()["pago_id"])
    acto = _acto(session, pac, "80.00")
    from application.services.caja_service import CajaService
    CajaService(session, 1).aplicar_saldo(pac.id)
    deuda = _cargo(session, acto)
    assert deuda.importe_pendiente == Decimal("80.00")

    r = client.patch(f"/pacientes/{pac.id}/pagos/{pago.id}/liberar", headers=_h(token))
    assert r.status_code == 200, r.text
    session.refresh(deuda)
    assert deuda.importe_pendiente == Decimal("0.00")
    assert CajaService(session, 1).saldo(pago) == Decimal("20.00")


def test_reasignar_pago_aplica_saldo_a_deuda_del_nuevo_presupuesto(
    client: TestClient, token: str, session: Session
):
    pac = _pac(session)
    pre_origen, _ = _presupuesto(session, pac)
    pre_destino = Presupuesto(centro_id=1, paciente_id=pac.id, fecha=date.today(),
                              estado_id=3, titulo="Nuevo presupuesto")
    session.add(pre_destino); session.commit(); session.refresh(pre_destino)
    t = _tto(session, f"Destino{pre_destino.id}")
    linea = PresupuestoLinea(presupuesto_id=pre_destino.id, tratamiento_id=t.id,
                             precio_unitario=Decimal("300"), cantidad=1)
    session.add(linea); session.commit(); session.refresh(linea)

    cobro = _cobro(client, token, pac, importe=100, presupuesto_id=pre_origen.id)
    assert cobro.status_code == 201, cobro.text
    pago = session.get(Pago, cobro.json()["pago_id"])
    acto = _acto(session, pac, "80.00", linea=linea)
    from application.services.caja_service import CajaService
    CajaService(session, 1).aplicar_saldo(pac.id)
    deuda = _cargo(session, acto)
    assert deuda.importe_pendiente == Decimal("80.00")

    r = client.patch(f"/pacientes/{pac.id}/pagos/{pago.id}/reasignar",
                     headers=_h(token), json={"presupuesto_id": pre_destino.id})
    assert r.status_code == 200, r.text
    session.refresh(deuda)
    assert deuda.importe_pendiente == Decimal("0.00")
    assert session.exec(select(DeudaPago).where(
        DeudaPago.pago_id == pago.id, DeudaPago.deuda_id == deuda.id
    )).one().pagado == Decimal("80.00")


def test_pago_historico_no_se_puede_reasignar(client: TestClient, token: str, session: Session):
    pac = _pac(session)
    historico = Pago(centro_id=1, paciente_id=pac.id, fecha=date(2019, 2, 1),
                     importe=Decimal("100.00"), forma_pago_id=2, origen="GELITE:PagoCli")
    session.add(historico); session.commit(); session.refresh(historico)

    r = client.patch(f"/pacientes/{pac.id}/pagos/{historico.id}/reasignar",
                     headers=_h(token), json={"presupuesto_id": None})
    assert r.status_code == 400


def test_cierre_consulta_crea_cargo_y_aplica_pago_a_cuenta_en_la_misma_operacion(
    client: TestClient, token: str, session: Session
):
    pac = _pac(session)
    assert _cobro(client, token, pac, importe=60).status_code == 201
    usuario_id = client.get("/auth/me", headers=_h(token)).json()["usuario_id"]
    periodo = UsuarioPeriodo(usuario_id=usuario_id, centro_id=1, orden=1, staff_tipo="DOCTOR",
                             fecha_alta=date.today())
    session.add(periodo); session.commit(); session.refresh(periodo)
    session.add(Colaborador(periodo_id=periodo.id)); session.commit()
    t = _tto(session, "Obturación cierre consulta")

    r = client.post(f"/pacientes/{pac.id}/consulta/cerrar", headers=_h(token), json={
        "tratamientos": [{"texto": t.nombre, "precio": 100}],
    })
    assert r.status_code == 201, r.text
    acto_id = r.json()["registrados"][0]["id"]
    acto = session.get(TratamientoRealizado, acto_id)
    deuda = _cargo(session, acto)
    assert deuda.adeudo == Decimal("100.00")
    assert deuda.importe_pendiente == Decimal("40.00")
    aplicado = session.exec(select(DeudaPago).where(DeudaPago.deuda_id == deuda.id)).all()
    assert sum((x.pagado for x in aplicado), Decimal("0")) == Decimal("60.00")
    plan = client.get(f"/pacientes/{pac.id}/plan", headers=_h(token)).json()
    assert plan["totales"]["pendiente"] == 40.0
    assert plan["totales"]["saldo_total"] == 40.0


# ── 2. PRESUPUESTO ───────────────────────────────────────────────────────────────────────
def test_pago_a_presupuesto_solo_paga_su_presupuesto(client: TestClient, token: str, session: Session):
    pac = _pac(session)
    pr, ln = _presupuesto(session, pac)
    ajeno = _acto(session, pac, "90.00", fecha=date(2026, 1, 1))              # fuera del presupuesto
    r = _cobro(client, token, pac, importe=300, presupuesto_id=pr.id)
    assert r.status_code == 201, r.text
    assert r.json()["saldo"] == 300.0                                        # no toca el acto ajeno
    dentro = _acto(session, pac, "300.00", linea=ln, fecha=date(2026, 3, 1))
    from application.services.caja_service import CajaService
    CajaService(session, 1).aplicar_saldo(pac.id)
    assert _cargo(session, dentro).liquidada
    assert session.exec(select(Deuda).where(Deuda.tratamiento_realizado_id == ajeno.id)).first() is None \
        or not _cargo(session, ajeno).liquidada


def test_presupuesto_no_aceptado_rechazado(client: TestClient, token: str, session: Session):
    pac = _pac(session)
    pr, _ = _presupuesto(session, pac, estado=1)                             # Entregado, no aceptado
    r = _cobro(client, token, pac, importe=100, presupuesto_id=pr.id)
    assert r.status_code == 422
    assert session.exec(select(Pago).where(Pago.paciente_id == pac.id)).all() == []


def test_presupuesto_de_otro_paciente_404(client: TestClient, token: str, session: Session):
    pac, otro = _pac(session), _pac(session)
    pr, _ = _presupuesto(session, otro)
    assert _cobro(client, token, pac, importe=100, presupuesto_id=pr.id).status_code == 404


def test_saldo_de_presupuesto_antes_que_a_cuenta(client: TestClient, token: str, session: Session):
    pac = _pac(session)
    pr, ln = _presupuesto(session, pac)
    p_cuenta = session.get(Pago, _cobro(client, token, pac, importe=100).json()["pago_id"])
    p_pre = session.get(Pago, _cobro(client, token, pac, importe=300, presupuesto_id=pr.id).json()["pago_id"])
    acto = _acto(session, pac, "250.00", linea=ln)
    from application.services.caja_service import CajaService
    caja = CajaService(session, 1); caja.aplicar_saldo(pac.id)
    assert _cargo(session, acto).liquidada
    assert caja.saldo(p_pre) == Decimal("50.00") and caja.saldo(p_cuenta) == Decimal("100.00")


# ── 1. TRATAMIENTO ───────────────────────────────────────────────────────────────────────
def test_pago_a_tratamiento_parcial_y_nunca_superior(client: TestClient, token: str, session: Session):
    pac = _pac(session); a = _acto(session, pac, "120.00")
    assert _cobro(client, token, pac, aplicaciones=[{"acto_id": a.id, "importe": 40}]).status_code == 201
    assert _cargo(session, a).importe_pendiente == Decimal("80.00")
    r = _cobro(client, token, pac, aplicaciones=[{"acto_id": a.id, "importe": 81}])
    assert r.status_code == 422                                              # supera lo pendiente


def test_pago_menor_que_lo_aplicado_rechazado(client: TestClient, token: str, session: Session):
    pac = _pac(session); a = _acto(session, pac, "120.00")
    r = _cobro(client, token, pac, importe=30, aplicaciones=[{"acto_id": a.id, "importe": 50}])
    assert r.status_code == 422


def test_sobrante_de_un_cobro_queda_a_cuenta(client: TestClient, token: str, session: Session):
    pac = _pac(session); a = _acto(session, pac, "120.00")
    r = _cobro(client, token, pac, importe=200, aplicaciones=[{"acto_id": a.id, "importe": 120}])
    assert r.status_code == 201, r.text
    assert r.json()["saldo"] == 80.0 and _cargo(session, a).liquidada


# ── "Realizado en esta cita": funcionaba con NameError (`p` no existía) y no tenía test ──────
# Usa SQL propio de PostgreSQL (now(), = ANY): en la base de pruebas SQLite no puede ejecutarse.
@pytest.mark.skipif(os.environ.get("DATABASE_URL", "").startswith("sqlite"),
                    reason="realizar-en-cita usa SQL de PostgreSQL; se verifica contra una copia PostgreSQL")
def test_realizar_en_cita_funciona_y_descuenta_del_saldo(client: TestClient, token: str, session: Session):
    pac = _pac(session); t = _tto(session, "Limpieza")
    assert _cobro(client, token, pac, importe=100).status_code == 201
    r = client.post(f"/pacientes/{pac.id}/presupuestos/realizar-en-cita", headers=_h(token),
                    json={"colaborador_id": 1, "lineas": [{"tratamiento_id": t.id, "precio": 60}]})
    assert r.status_code == 201, r.text
    acto = session.exec(select(TratamientoRealizado).where(
        TratamientoRealizado.paciente_id == pac.id, TratamientoRealizado.tratamiento_id == t.id)).one()
    d = _cargo(session, acto)
    assert d.liquidada and d.adeudo == Decimal("60.00")
    plan = client.get(f"/pacientes/{pac.id}/plan", headers=_h(token)).json()
    assert plan["totales"]["saldo_a_favor"] == 40.0


# ── Un pago migrado (origen GELITE:…) NO es saldo: ya pagó sus tratamientos en GELITE ─────────
def test_pago_migrado_no_se_gasta_en_tratamientos_nuevos(client: TestClient, token: str, session: Session):
    pac = _pac(session)
    viejo = Pago(centro_id=1, paciente_id=pac.id, fecha=date(2018, 5, 1), importe=Decimal("500"),
                 forma_pago_id=2, origen="GELITE:PagoCli")
    session.add(viejo); session.commit(); session.refresh(viejo)
    a = _acto(session, pac, "120.00")
    assert _cobro(client, token, pac, importe=50).status_code == 201         # dinero de la app
    d = _cargo(session, a)
    assert d.importe_pendiente == Decimal("70.00")                           # solo los 50 de la app
    assert session.exec(select(DeudaPago).where(DeudaPago.pago_id == viejo.id)).all() == []
    plan = client.get(f"/pacientes/{pac.id}/plan", headers=_h(token)).json()
    hist = [p for p in plan["pagos"] if p["id"] == viejo.id][0]
    assert hist["saldo"] == 0.0 and hist["asociado_a"] == "Histórico GELITE"
    assert plan["totales"]["saldo_a_favor"] == 0.0
