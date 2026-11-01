"""Tests de M02 Config: fuente de verdad jerárquica + permiso config.editar."""
from fastapi.testclient import TestClient
from sqlmodel import Session

from application.services.config_service import ConfigService


def test_get_config_devuelve_valores_efectivos(client: TestClient, auth_headers: dict):
    resp = client.get("/config", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    # Centro gana sobre global (seed: global "MakingSmiles", centro "Clínica Demo").
    assert body["valores"]["marca.nombre"] == "Clínica Demo"


def test_set_config_con_permiso(client: TestClient, auth_headers: dict):
    resp = client.put("/config", json={"clave": "agenda.vista_defecto", "valor": "mes"},
                      headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["clave"] == "agenda.vista_defecto"
    assert body["valor"] == "mes"


def test_resolve_jerarquia(session: Session):
    svc = ConfigService(session)
    # Centro (id=1) gana sobre global para marca.nombre.
    assert svc.resolve("marca.nombre") == "MakingSmiles"
    assert svc.resolve("marca.nombre", centro_id=1) == "Clínica Demo"
    # Clave ausente → default.
    assert svc.resolve("no.existe", default=42) == 42
