"""Tests de M03 (sub-pieza): catálogo geográfico oficial."""
from fastapi.testclient import TestClient


def test_paises_requiere_auth(client: TestClient):
    assert client.get("/geo/paises").status_code == 401


def test_paises_con_auth(client: TestClient, auth_headers: dict):
    r = client.get("/geo/paises", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_buscar_cp_con_auth(client: TestClient, auth_headers: dict):
    r = client.get("/geo/buscar-cp/28921", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
