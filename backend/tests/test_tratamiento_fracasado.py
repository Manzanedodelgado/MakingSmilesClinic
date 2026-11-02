"""Tratamiento fracasado: abono en negativo + crédito a favor (CajaService, un solo dueño)."""
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from domain.models.core import Paciente, Tratamiento
from domain.models.economico import TratamientoRealizado
from domain.models.gestoria import Deuda


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _acto(session: Session, **extra) -> tuple[Paciente, TratamientoRealizado]:
    p = Paciente(centro_id=1, nombre="Fracaso", apellidos="Prueba")
    t = Tratamiento(centro_id=1, nombre="Obturación", codigo="OBF", activo=True)
    session.add(p); session.add(t); session.commit(); session.refresh(p); session.refresh(t)
    a = TratamientoRealizado(centro_id=1, paciente_id=p.id, tratamiento_id=t.id, fecha_inicio=date.today(),
                             importe=Decimal("100.00"), estado_id=5, piezas="16", **extra)
    session.add(a); session.commit(); session.refresh(a)
    return p, a


def test_abono_y_credito_y_no_se_repite(client: TestClient, token: str, session: Session):
    p, a = _acto(session)
    r = client.post(f"/pacientes/{p.id}/actos/{a.id}/marcar-fracasado", headers=_h(token))
    assert r.status_code == 201, r.text
    espejo = session.get(TratamientoRealizado, r.json()["acto_abono_id"])
    assert espejo.importe == Decimal("-100.00") and espejo.num_transaccion.startswith(f"ABONO_TTO:{a.id}:")
    credito = session.get(Deuda, r.json()["deuda_credito_id"])
    assert credito.importe_pendiente == Decimal("-100.00") and credito.liquidada
    assert session.get(TratamientoRealizado, a.id).importe == Decimal("100.00")   # el original no se toca
    r2 = client.post(f"/pacientes/{p.id}/actos/{a.id}/marcar-fracasado", headers=_h(token))
    assert r2.status_code == 409


def test_acto_facturado_sin_anular_da_409(client: TestClient, token: str, session: Session):
    p, a = _acto(session, num_factura_e="F-1")
    r = client.post(f"/pacientes/{p.id}/actos/{a.id}/marcar-fracasado", headers=_h(token))
    assert r.status_code == 409, r.text
    assert len(session.exec(select(TratamientoRealizado).where(TratamientoRealizado.paciente_id == p.id)).all()) == 1


def test_acto_de_otro_paciente_404(client: TestClient, token: str, session: Session):
    p, a = _acto(session)
    otro = Paciente(centro_id=1, nombre="Otro", apellidos="Paciente"); session.add(otro); session.commit()
    r = client.post(f"/pacientes/{otro.id}/actos/{a.id}/marcar-fracasado", headers=_h(token))
    assert r.status_code == 404
