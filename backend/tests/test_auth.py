"""Tests de M01 Identidad: login, cookie, /auth/me y RBAC multi-tenant."""
from fastapi.testclient import TestClient

from main import app


def test_login_bearer_devuelve_token(client: TestClient):
    resp = client.post("/auth/login", json={
        "email": "admin@makingsmiles.local", "password": "admin1234",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["usuario"]["email"] == "admin@makingsmiles.local"
    assert body["accesos"]


def test_login_cookie_no_devuelve_token_en_json(client: TestClient):
    resp = client.post("/auth/login-cookie", json={
        "email": "admin@makingsmiles.local", "password": "admin1234",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" not in body
    assert resp.cookies.get("access_token")


def test_login_incorrecto_da_401(client: TestClient):
    resp = client.post("/auth/login", json={
        "email": "admin@makingsmiles.local", "password": "incorrecta",
    })
    assert resp.status_code == 401


def test_me_con_token(client: TestClient, auth_headers: dict):
    resp = client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["nombre"] == "Admin Demo"
    assert "config.editar" in body["permisos"]
    assert body["centro_activo"] is not None
    assert body["centro_nombre"] == "Rubio García Dental"


def test_me_sin_token_da_401(client: TestClient):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_centro_ajeno_da_403(client: TestClient, auth_headers: dict):
    resp = client.get("/auth/me", headers={**auth_headers, "X-Centro-Id": "999"})
    assert resp.status_code == 403


def test_logout(client: TestClient):
    resp = client.post("/auth/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
