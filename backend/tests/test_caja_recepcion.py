"""Caja de recepción (INICIO): cargar el acto realizado y cobrarlo, enlazando deuda↔pago."""
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from domain.models.core import Paciente, Tratamiento
from domain.models.economico import Pago, TratamientoRealizado
from domain.models.gestoria import Deuda, DeudaPago


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _pac(session: Session, centro_id: int = 1) -> Paciente:
    p = Paciente(centro_id=centro_id, nombre="Caja", apellidos=f"Prueba {centro_id}")
    session.add(p); session.commit(); session.refresh(p)
    return p


def _acto(session: Session, pac: Paciente, importe: str = "120.00") -> TratamientoRealizado:
    t = Tratamiento(centro_id=pac.centro_id, nombre="Obturación", codigo=f"OB{pac.id}", activo=True)
    session.add(t); session.commit(); session.refresh(t)
    a = TratamientoRealizado(centro_id=pac.centro_id, paciente_id=pac.id, tratamiento_id=t.id,
                             fecha_inicio=date.today(), importe=Decimal(importe), estado_id=5, piezas="16")
    session.add(a); session.commit(); session.refresh(a)
    return a


def test_caja_lista_acto_sin_cargo(client: TestClient, token: str, session: Session):
    pac = _pac(session); a = _acto(session, pac)
    r = client.get(f"/inicio/paciente/{pac.id}/caja", headers=_h(token))
    assert r.status_code == 200, r.text
    j = r.json()
    assert [x["acto_id"] for x in j["actos"]] == [a.id]
    assert j["actos"][0]["concepto"] == "Obturación"
    assert j["total"] == 120.0
    assert "Pago Eurodent" not in [f["nombre"] for f in j["formas"]] and "Bizum" in [f["nombre"] for f in j["formas"]]


def test_cobro_parcial_y_total_enlaza_deuda_y_pago(client: TestClient, token: str, session: Session):
    pac = _pac(session); a = _acto(session, pac)
    r = client.post(f"/inicio/paciente/{pac.id}/cobro", headers=_h(token),
                    json={"forma_pago_id": 6, "aplicaciones": [{"acto_id": a.id, "importe": 50}]})
    assert r.status_code == 201, r.text
    d = session.exec(select(Deuda).where(Deuda.tratamiento_realizado_id == a.id)).one()
    session.refresh(d)
    assert d.adeudo == Decimal("120.00") and d.importe_pendiente == Decimal("70.00") and not d.liquidada
    pago = session.get(Pago, r.json()["pago_id"])
    assert pago.forma_pago_id == 6 and pago.cliente_id == pac.cliente_id and pago.importe == Decimal("50.00")
    assert session.exec(select(DeudaPago).where(DeudaPago.pago_id == pago.id)).one().deuda_id == d.id

    caja = client.get(f"/inicio/paciente/{pac.id}/caja", headers=_h(token)).json()
    assert caja["actos"] == [] and caja["deudas"][0]["pendiente"] == 70.0

    r2 = client.post(f"/inicio/paciente/{pac.id}/cobro", headers=_h(token),
                     json={"forma_pago_id": 2, "aplicaciones": [{"deuda_id": d.id, "importe": 70}]})
    assert r2.status_code == 201, r2.text
    session.refresh(d)
    assert d.liquidada and d.importe_pendiente == Decimal("0.00")
    assert client.get(f"/inicio/paciente/{pac.id}/caja", headers=_h(token)).json()["total"] == 0


def test_cobro_no_supera_lo_pendiente(client: TestClient, token: str, session: Session):
    pac = _pac(session); a = _acto(session, pac)
    r = client.post(f"/inicio/paciente/{pac.id}/cobro", headers=_h(token),
                    json={"forma_pago_id": 2, "aplicaciones": [{"acto_id": a.id, "importe": 500}]})
    assert r.status_code == 422
    assert session.exec(select(Pago).where(Pago.paciente_id == pac.id)).all() == []
    assert session.exec(select(Deuda).where(Deuda.paciente_id == pac.id)).all() == []


def test_forma_pago_invalida(client: TestClient, token: str, session: Session):
    pac = _pac(session); a = _acto(session, pac)
    r = client.post(f"/inicio/paciente/{pac.id}/cobro", headers=_h(token),
                    json={"forma_pago_id": 14, "aplicaciones": [{"acto_id": a.id, "importe": 10}]})
    assert r.status_code == 422


def test_acto_de_otro_paciente_rechazado(client: TestClient, token: str, session: Session):
    pa = _pac(session); pb = _pac(session); ab = _acto(session, pb)
    r = client.post(f"/inicio/paciente/{pa.id}/cobro", headers=_h(token),
                    json={"forma_pago_id": 2, "aplicaciones": [{"acto_id": ab.id, "importe": 10}]})
    assert r.status_code == 404
    assert session.exec(select(Deuda).where(Deuda.tratamiento_realizado_id == ab.id)).all() == []


def test_paciente_de_otro_centro_404(client: TestClient, token: str, session: Session):
    ajeno = _pac(session, centro_id=999)
    assert client.get(f"/inicio/paciente/{ajeno.id}/caja", headers=_h(token)).status_code == 404


def test_acto_migrado_de_gelite_no_es_cobrable(client: TestClient, token: str, session: Session):
    """Los actos de GELITE (num_tto) ya tienen su cargo importado en `deudas`, sin enlazar al
    acto: cargarlos otra vez cobraría dos veces lo mismo."""
    pac = _pac(session); a = _acto(session, pac)
    a.num_tto = 123456; session.add(a); session.commit()
    assert client.get(f"/inicio/paciente/{pac.id}/caja", headers=_h(token)).json()["actos"] == []
    r = client.post(f"/inicio/paciente/{pac.id}/cobro", headers=_h(token),
                    json={"forma_pago_id": 2, "aplicaciones": [{"acto_id": a.id, "importe": 10}]})
    assert r.status_code == 422
    assert session.exec(select(Deuda).where(Deuda.paciente_id == pac.id)).all() == []


def test_formas_pago_catalogo_unico(client: TestClient, token: str):
    r = client.get("/pacientes/formas-pago", headers=_h(token))
    assert r.status_code == 200, r.text
    nombres = [f["nombre"] for f in r.json()["formas"]]
    assert nombres[:3] == ["Efectivo", "Tarjeta de crédito", "Bizum"]
    assert "Pago Eurodent" not in nombres          # no se ofrece al cobrar
    todas = client.get("/pacientes/formas-pago?solo_caja=false", headers=_h(token)).json()["formas"]
    assert len(todas) == 16


def test_cobro_plan_economico_financiacion(client: TestClient, token: str, session: Session):
    pac = _pac(session)
    d = Deuda(centro_id=1, paciente_id=pac.id, fecha_plazo=date.today(), adeudo=Decimal("1000.00"),
              importe_pendiente=Decimal("1000.00"))
    session.add(d); session.commit(); session.refresh(d)
    r = client.post(f"/pacientes/{pac.id}/pagos", headers=_h(token),
                    json={"deuda_id": d.id, "fecha": date.today().isoformat(), "importe": 1000,
                          "forma_pago_id": 8, "neto": 950})
    assert r.status_code == 201, r.text
    assert r.json()["costeFinanciero"] == 50.0
    pago = session.get(Pago, r.json()["pagoId"])
    assert pago.forma_pago_id == 8 and pago.neto == Decimal("950.00") and pago.importe == Decimal("1000.00")


# ── 23-oct-2026: los cobros quedan auditados y validan neto y financiera ──

def test_cobro_queda_en_auditoria(client: TestClient, token: str, session: Session):
    from domain.models.auditoria import Auditoria
    pac = _pac(session); a = _acto(session, pac)
    r = client.post(f"/inicio/paciente/{pac.id}/cobro", headers=_h(token),
                    json={"forma_pago_id": 6, "aplicaciones": [{"acto_id": a.id, "importe": 30}]})
    assert r.status_code == 201, r.text
    fila = session.exec(select(Auditoria).where(Auditoria.accion == "pagos.cobrar",
                                                Auditoria.recurso == f"pago:{r.json()['pago_id']}")).first()
    assert fila is not None and fila.detalle["paciente_id"] == pac.id


def test_neto_mayor_que_el_importe_rechazado(client: TestClient, token: str, session: Session):
    pac = _pac(session)
    d = Deuda(centro_id=1, paciente_id=pac.id, fecha_plazo=date.today(), adeudo=Decimal("100.00"),
              importe_pendiente=Decimal("100.00"))
    session.add(d); session.commit(); session.refresh(d)
    r = client.post(f"/pacientes/{pac.id}/pagos", headers=_h(token),
                    json={"deuda_id": d.id, "fecha": date.today().isoformat(), "importe": 100,
                          "forma_pago_id": 8, "neto": 150})
    assert r.status_code == 422, r.text
    assert session.exec(select(Pago).where(Pago.paciente_id == pac.id)).first() is None


def test_financiera_de_otro_centro_rechazada(client: TestClient, token: str, session: Session):
    from domain.models.core import Centro
    from domain.models.economico import Financiera
    otro = Centro(nombre="Otro centro")
    session.add(otro); session.commit(); session.refresh(otro)
    fin = Financiera(centro_id=otro.id, nombre="Ajena")
    session.add(fin); session.commit(); session.refresh(fin)
    pac = _pac(session)
    r = client.post(f"/pacientes/{pac.id}/pagos", headers=_h(token),
                    json={"fecha": date.today().isoformat(), "importe": 100, "forma_pago_id": 8,
                          "financiera_id": fin.id})
    assert r.status_code == 404, r.text
