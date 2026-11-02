"""Tests de M05: agenda (referencias, citas, huecos) y reglas de cita activas."""
from fastapi.testclient import TestClient


def test_citas_requiere_auth(client: TestClient):
    assert client.get("/agenda/citas").status_code == 401


def test_referencias_con_auth(client: TestClient, auth_headers: dict):
    r = client.get("/agenda/referencias", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)


def test_citas_con_auth(client: TestClient, auth_headers: dict):
    r = client.get("/agenda/citas", params={"fecha": "2026-11-02"}, headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), (dict, list))


def test_cita_sin_datos_obligatorios_rechazada(client: TestClient, auth_headers: dict):
    """cita_reglas registradas: una cita sin gabinete/tipo/duración/teléfono se rechaza."""
    r = client.post("/agenda/citas", json={}, headers=auth_headers)
    assert r.status_code in (400, 422)
