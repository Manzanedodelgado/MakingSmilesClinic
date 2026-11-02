"""Tests F0 — Genoma: CENTINELA (auth/RBAC) + CEREBRO (config jerárquica)."""
from fastapi.testclient import TestClient


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ───────────────────────── CENTINELA · auth ─────────────────────────
def test_login_ok(client: TestClient):
    resp = client.post("/auth/login", json={
        "email": "admin@makingsmiles.local", "password": "admin1234",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert len(body["accesos"]) == 1


def test_login_cookie_no_expone_jwt_en_respuesta(client: TestClient):
    resp = client.post("/auth/login-cookie", json={
        "email": "admin@makingsmiles.local", "password": "admin1234",
    })
    assert resp.status_code == 200
    assert "access_token" not in resp.json()
    assert "httponly" in resp.headers["set-cookie"].lower()


def test_forgot_ignora_origin_no_confiable(client: TestClient, monkeypatch):
    from application.services import auth_service
    enviados = []
    monkeypatch.setattr(auth_service, "send_email", lambda session, email, subject, html: enviados.append(html) or True)
    resp = client.post("/auth/forgot", headers={"Origin": "https://dominio-atacante.example"},
                       json={"email": "admin@makingsmiles.local"})
    assert resp.status_code == 200
    assert enviados
    assert "dominio-atacante.example" not in enviados[0]
    from domain.config.settings import settings
    assert settings.public_frontend_url in enviados[0]  # el enlace usa SIEMPRE el origen canónico configurado


def test_login_bad_password(client: TestClient):
    resp = client.post("/auth/login", json={
        "email": "admin@makingsmiles.local", "password": "WRONG",
    })
    assert resp.status_code == 401


def test_me_requires_token(client: TestClient):
    assert client.get("/auth/me").status_code == 401


def test_me_ok(client: TestClient, token: str):
    resp = client.get("/auth/me", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["nombre"] == "Admin Demo"
    assert "config.editar" in body["permisos"]
    assert body["centro_activo"] == 1


# ───────────────────────── CEREBRO · config ─────────────────────────
def test_config_hierarchy_centro_overrides_global(client: TestClient, token: str):
    """marca.nombre tiene global 'MakingSmiles' y override de centro 'Clínica Demo'."""
    resp = client.get("/config", headers=_auth(token))
    assert resp.status_code == 200
    valores = resp.json()["valores"]
    assert valores["marca.nombre"] == "Clínica Demo"  # el centro gana al global


def test_config_sistema_scope(client: TestClient, token: str):
    resp = client.get("/config", params={"sistema": "cuidarte"}, headers=_auth(token))
    valores = resp.json()["valores"]
    assert valores["agenda.intervalo_min"] == 15
    assert valores["agenda.vista_defecto"] == "semana"


def test_config_set_requires_permission(client: TestClient, token: str):
    """Con permiso config.editar (rol Administrador) el PUT entra y persiste."""
    resp = client.put("/config", headers=_auth(token), json={
        "clave": "agenda.intervalo_min", "valor": 30, "sistema": "cuidarte",
    })
    assert resp.status_code == 200
    # Releemos: el nuevo valor manda
    again = client.get("/config", params={"sistema": "cuidarte"}, headers=_auth(token))
    assert again.json()["valores"]["agenda.intervalo_min"] == 30


def test_config_set_denied_without_permission(client: TestClient, session):
    """Un usuario cuyo rol NO tiene config.editar recibe 403 al escribir config."""
    from datetime import date
    from domain.models.identidad import (
        Permiso, Rol, RolePermiso, Usuario, UserCenterRole, UsuarioPeriodo,
    )
    from infrastructure.security import hash_password
    from sqlmodel import select

    # Rol 'Recepción' con solo config.ver (sin editar)
    rol = Rol(centro_id=1, nombre="Recepción")
    session.add(rol); session.commit(); session.refresh(rol)
    ver = session.exec(select(Permiso).where(Permiso.codigo == "config.ver")).first()
    session.add(RolePermiso(rol_id=rol.id, permiso_id=ver.id))
    user = Usuario(email="recep@demo.local", nombre="Recepción",
                   password_hash=hash_password("recep1234"))
    session.add(user); session.commit(); session.refresh(user)
    session.add(UserCenterRole(usuario_id=user.id, centro_id=1, rol_id=rol.id))
    session.add(UsuarioPeriodo(usuario_id=user.id, centro_id=1, orden=0, staff_tipo="RECEPCION", fecha_alta=date(2026, 1, 1)))
    session.commit()

    tok = client.post("/auth/login", json={
        "email": "recep@demo.local", "password": "recep1234",
    }).json()["access_token"]
    resp = client.put("/config", headers=_auth(tok),
                      json={"clave": "agenda.intervalo_min", "valor": 99, "sistema": "cuidarte"})
    assert resp.status_code == 403


def test_config_write_is_audited(client: TestClient, token: str, session):
    from sqlmodel import select
    from domain.models.auditoria import Auditoria

    client.put("/config", headers=_auth(token), json={"clave": "x.y", "valor": 1})
    filas = session.exec(select(Auditoria).where(Auditoria.accion == "config.set")).all()
    assert len(filas) >= 1
    assert filas[0].usuario_id == 1
