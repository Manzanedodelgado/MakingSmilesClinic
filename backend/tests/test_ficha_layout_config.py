"""Confirma que la clave ficha_layout (feature: cajas movibles de la ficha de paciente)
funciona con el ConfigService genérico tal cual está, sin código backend nuevo."""
from fastapi.testclient import TestClient


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


LAYOUT_EJEMPLO = [
    {"i": "odontograma", "x": 6, "y": 0, "w": 6, "h": 10},
    {"i": "historial", "x": 0, "y": 0, "w": 6, "h": 10},
    {"i": "nuevo_acto", "x": 0, "y": 10, "w": 6, "h": 8},
    {"i": "multimedia", "x": 6, "y": 10, "w": 6, "h": 8},
]


def test_ficha_layout_set_and_get(client: TestClient, token: str):
    put = client.put("/config", headers=_auth(token), json={
        "clave": "ficha_layout", "valor": LAYOUT_EJEMPLO, "sistema": "pacientes",
    })
    assert put.status_code == 200

    get = client.get("/config", params={"sistema": "pacientes"}, headers=_auth(token))
    assert get.status_code == 200
    assert get.json()["valores"]["ficha_layout"] == LAYOUT_EJEMPLO


def test_ficha_layout_denied_without_permission(client: TestClient, session):
    """Mismo patrón que test_config_set_denied_without_permission: rol sin config.editar → 403."""
    from datetime import date
    from domain.models.identidad import (
        Permiso, Rol, RolePermiso, Usuario, UserCenterRole, UsuarioPeriodo,
    )
    from infrastructure.security import hash_password
    from sqlmodel import select

    rol = Rol(centro_id=1, nombre="Recepción FL")
    session.add(rol); session.commit(); session.refresh(rol)
    ver = session.exec(select(Permiso).where(Permiso.codigo == "config.ver")).first()
    session.add(RolePermiso(rol_id=rol.id, permiso_id=ver.id))
    user = Usuario(email="recep-fl@demo.local", nombre="Recepción FL",
                   password_hash=hash_password("recep1234"))
    session.add(user); session.commit(); session.refresh(user)
    session.add(UserCenterRole(usuario_id=user.id, centro_id=1, rol_id=rol.id))
    session.add(UsuarioPeriodo(usuario_id=user.id, centro_id=1, orden=0, staff_tipo="RECEPCION", fecha_alta=date(2026, 1, 1)))
    session.commit()

    tok = client.post("/auth/login", json={
        "email": "recep-fl@demo.local", "password": "recep1234",
    }).json()["access_token"]
    resp = client.put("/config", headers=_auth(tok),
                      json={"clave": "ficha_layout", "valor": LAYOUT_EJEMPLO, "sistema": "pacientes"})
    assert resp.status_code == 403
