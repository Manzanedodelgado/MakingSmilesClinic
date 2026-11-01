"""Tests de M01: alta de personal y roles (configuracion_staff / configuracion_roles)."""
from fastapi.testclient import TestClient


def test_list_personal(client: TestClient, auth_headers: dict):
    r = client.get("/configuracion/personal", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert any(u["email"] == "admin@makingsmiles.local" for u in body["personal"])


def test_list_roles(client: TestClient, auth_headers: dict):
    r = client.get("/configuracion/roles", headers=auth_headers)
    assert r.status_code == 200
    roles = r.json()["roles"]
    assert any(rl["nombre"] == "Administrador" for rl in roles)


def test_crear_rol(client: TestClient, auth_headers: dict):
    r = client.post("/configuracion/roles", json={
        "nombre": "Recepcionista", "permisos": ["citas.ver", "citas.editar"],
    }, headers=auth_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["nombre"] == "Recepcionista"
    assert set(body["permisos"]) == {"citas.ver", "citas.editar"}


def test_crear_personal(client: TestClient, auth_headers: dict):
    r = client.post("/configuracion/personal", json={
        "nombre": "Nueva", "apellidos": "Persona",
        "email": "nueva@test.local", "password": "123456",
    }, headers=auth_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["nombre"] == "Nueva"
    assert body["tiene_login"] is True
    assert body["rol_nombre"] == "Administrador"  # rol por defecto


def test_list_personal_sin_token_da_401(client: TestClient):
    r = client.get("/configuracion/personal")
    assert r.status_code == 401
