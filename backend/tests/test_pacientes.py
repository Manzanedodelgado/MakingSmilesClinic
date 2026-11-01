"""Tests de M03: núcleo de pacientes (ficha autenticada, anti-IDOR, PII retirada)."""
import pytest

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from domain.models.core import Centro, Paciente


def _crear_paciente(session: Session, **kw) -> Paciente:
    centro_id = session.exec(select(Centro.id)).first()
    p = Paciente(centro_id=centro_id, activo=True, **kw)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_get_paciente_requiere_auth(client: TestClient, session: Session):
    p = _crear_paciente(session, nombre="Juan", apellidos="García")
    r = client.get(f"/pacientes/{p.id}")
    assert r.status_code == 401


def test_get_paciente_autenticado(client: TestClient, session: Session, auth_headers: dict):
    p = _crear_paciente(session, nombre="Juan", apellidos="García", num_historia="1001")
    r = client.get(f"/pacientes/{p.id}", headers=auth_headers)
    assert r.status_code == 200


def test_buscar_pacientes(client: TestClient, session: Session, auth_headers: dict):
    """Búsqueda usa regex/word-boundary de Postgres (\\m...\\M), no disponible en SQLite."""
    pytest.skip("endpoint Postgres-only (regex \\m/\\M); no testeable sobre SQLite")


def test_pii_ficha_retirada(client: TestClient, session: Session, auth_headers: dict):
    """S1/S2: las rutas PII sin auth ya no existen (corrección documentada)."""
    p = _crear_paciente(session, nombre="Juan", apellidos="García")
    r = client.get(f"/pacientes/{p.id}/ficha", headers=auth_headers)
    assert r.status_code == 404
    r2 = client.get(f"/pacientes/{p.id}/citas", headers=auth_headers)
    assert r2.status_code == 404
