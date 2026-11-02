"""Tests de M07: clínica / consulta / cefalometría (catálogos y lectura por paciente)."""
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


def test_catalogo_recomendaciones(client: TestClient, auth_headers: dict):
    r = client.get("/pacientes/recomendaciones/catalogo", headers=auth_headers)
    assert r.status_code == 200


def test_cefalometria_definicion(client: TestClient, auth_headers: dict):
    r = client.get("/cefalometria/definicion", headers=auth_headers)
    assert r.status_code == 200


def test_alertas_paciente(client: TestClient, session: Session, auth_headers: dict):
    p = _paciente(session, nombre="Ana", apellidos="Ruiz")
    r = client.get(f"/pacientes/{p.id}/alertas", headers=auth_headers)
    assert r.status_code == 200


def test_alertas_sin_auth(client: TestClient, session: Session):
    p = _paciente(session, nombre="Luis", apellidos="Soto")
    assert client.get(f"/pacientes/{p.id}/alertas").status_code == 401


def test_recetas_paciente(client: TestClient, session: Session, auth_headers: dict):
    p = _paciente(session, nombre="Eva", apellidos="Marín")
    r = client.get(f"/pacientes/{p.id}/recetas", headers=auth_headers)
    assert r.status_code == 200
