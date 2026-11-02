"""Tests de M09: consentimientos (plantillas, por paciente, auth)."""
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from domain.models.core import Centro, Paciente


def _paciente(session: Session, **kw) -> Paciente:
    centro_id = session.exec(select(Centro.id)).first()
    p = Paciente(centro_id=centro_id, activo=True, **kw)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_plantillas_requiere_auth(client: TestClient):
    assert client.get("/consentimientos/plantillas").status_code == 401


def test_plantillas_con_auth(client: TestClient, auth_headers: dict):
    r = client.get("/consentimientos/plantillas", headers=auth_headers)
    assert r.status_code == 200


def test_consentimientos_de_paciente(client: TestClient, session: Session, auth_headers: dict):
    p = _paciente(session, nombre="Paco", apellidos="Gil")
    r = client.get(f"/consentimientos/paciente/{p.id}", headers=auth_headers)
    assert r.status_code == 200
