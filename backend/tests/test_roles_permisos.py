"""Roles y permisos: efectivos = (rol − límites por persona) ∪ directos; edición de roles."""
from datetime import date

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from application.services.auth_service import AuthService
from domain.models.identidad import (
    Permiso, Rol, RolePermiso, Usuario, UserCenterPermiso, UserCenterPermisoDenegado, UserCenterRole, UsuarioPeriodo,
)


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _persona(client, token, rol_id, permisos, nombre="Prueba"):
    r = client.post("/configuracion/personal", headers=_h(token), json={
        "nombre": nombre, "staff_tipo": "RECEPCION", "fecha_alta": str(date(2026, 1, 1)),
        "rol_id": rol_id, "permisos": permisos})
    return r


def _asegura(session, codigos):
    for c in codigos:
        if not session.exec(select(Permiso).where(Permiso.codigo == c)).first():
            session.add(Permiso(codigo=c, descripcion=c))
    session.commit()


def _rol(client, token, nombre, permisos):
    r = client.post("/configuracion/roles", headers=_h(token), json={"nombre": nombre, "permisos": permisos})
    assert r.status_code == 201, r.text
    return r.json()


def test_efectivos_son_rol_menos_limites_mas_directos(session: Session):
    centro_id = 1
    rol = Rol(centro_id=centro_id, nombre="Recepción"); session.add(rol); session.commit(); session.refresh(rol)
    ids = {p.codigo: p.id for p in session.exec(select(Permiso)).all()}
    for c in ("citas.ver", "citas.editar", "pacientes.ver"):
        session.add(RolePermiso(rol_id=rol.id, permiso_id=ids[c]))
    u = Usuario(nombre="Ana", email="ana@x.local"); session.add(u); session.commit(); session.refresh(u)
    session.add(UserCenterRole(usuario_id=u.id, centro_id=centro_id, rol_id=rol.id))
    session.add(UserCenterPermisoDenegado(usuario_id=u.id, centro_id=centro_id, permiso_id=ids["citas.editar"]))
    session.add(UserCenterPermiso(usuario_id=u.id, centro_id=centro_id, permiso_id=ids["gestoria.ver"]))
    session.commit()
    assert AuthService(session).permisos_de(u.id, centro_id) == {"citas.ver", "pacientes.ver", "gestoria.ver"}


def test_superuser_nunca_viene_de_un_rol(session: Session):
    rol = Rol(centro_id=1, nombre="Raro"); session.add(rol); session.commit(); session.refresh(rol)
    su = session.exec(select(Permiso).where(Permiso.codigo == "superuser")).first()
    if su is None:
        su = Permiso(codigo="superuser", descripcion="plataforma"); session.add(su); session.commit(); session.refresh(su)
    session.add(RolePermiso(rol_id=rol.id, permiso_id=su.id))
    u = Usuario(nombre="Zed", email="zed@x.local"); session.add(u); session.commit(); session.refresh(u)
    session.add(UserCenterRole(usuario_id=u.id, centro_id=1, rol_id=rol.id)); session.commit()
    assert "superuser" not in AuthService(session).permisos_de(u.id, 1)


def test_crud_de_roles(client: TestClient, token: str):
    r = _rol(client, token, "Gestoría", ["gestoria.ver"])
    assert r["permisos"] == ["gestoria.ver"] and r["usuarios"] == 0
    lst = client.get("/configuracion/roles", headers=_h(token)).json()
    assert {x["nombre"] for x in lst["roles"]} >= {"Administrador", "Gestoría"}
    assert client.post("/configuracion/roles", headers=_h(token),
                       json={"nombre": "gestoría", "permisos": []}).status_code == 409   # duplicado sin mayúsculas
    assert client.post("/configuracion/roles", headers=_h(token),
                       json={"nombre": "X", "permisos": ["superuser"]}).status_code == 400
    e = client.put(f"/configuracion/roles/{r['id']}", headers=_h(token),
                   json={"nombre": "Gestoría", "permisos": ["gestoria.ver", "gestoria.editar"]})
    assert e.status_code == 200 and e.json()["permisos"] == ["gestoria.editar", "gestoria.ver"]
    assert client.delete(f"/configuracion/roles/{r['id']}", headers=_h(token)).status_code == 204


def test_rol_administrador_protegido(client: TestClient, token: str):
    admin = next(x for x in client.get("/configuracion/roles", headers=_h(token)).json()["roles"]
                 if x["nombre"] == "Administrador")
    assert client.delete(f"/configuracion/roles/{admin['id']}", headers=_h(token)).status_code == 400
    assert client.put(f"/configuracion/roles/{admin['id']}", headers=_h(token),
                      json={"nombre": "Otro", "permisos": admin["permisos"]}).status_code == 400
    sin_config = [p for p in admin["permisos"] if not p.startswith("config.")]
    assert client.put(f"/configuracion/roles/{admin['id']}", headers=_h(token),
                      json={"nombre": "Administrador", "permisos": sin_config}).status_code == 400


def test_no_se_borra_un_rol_con_personas(client: TestClient, token: str):
    rol = _rol(client, token, "Citas", ["citas.ver"])
    assert _persona(client, token, rol["id"], ["citas.ver"]).status_code == 201
    assert client.delete(f"/configuracion/roles/{rol['id']}", headers=_h(token)).status_code == 409


def test_limitar_permisos_de_una_persona_y_no_ampliar(client: TestClient, token: str, session: Session):
    rol = _rol(client, token, "Recepción", ["citas.ver", "citas.editar", "pacientes.ver"])
    r = _persona(client, token, rol["id"], ["citas.ver", "pacientes.ver"])   # limita: sin citas.editar
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["permisos"] == ["citas.ver", "pacientes.ver"]
    assert p["permisos_rol"] == ["citas.editar", "citas.ver", "pacientes.ver"]
    # ampliar por encima del rol se rechaza
    r2 = client.put(f"/configuracion/personal/{p['id']}", headers=_h(token),
                    json={"nombre": "Prueba", "permisos": ["citas.ver", "gestoria.ver"]})
    assert r2.status_code == 400 and "gestoria.ver" in r2.text
    # volver a marcar todo lo del rol quita el límite
    r3 = client.put(f"/configuracion/personal/{p['id']}", headers=_h(token),
                    json={"nombre": "Prueba", "permisos": ["citas.ver", "citas.editar", "pacientes.ver"]})
    assert r3.status_code == 200 and r3.json()["permisos"] == ["citas.editar", "citas.ver", "pacientes.ver"]
    assert session.exec(select(UserCenterPermisoDenegado)).all() == []


def test_si_el_rol_pierde_un_permiso_se_limpia_el_limite(client: TestClient, token: str, session: Session):
    rol = _rol(client, token, "Mixto", ["citas.ver", "citas.editar"])
    p = _persona(client, token, rol["id"], ["citas.ver"], nombre="Mixta").json()
    assert len(session.exec(select(UserCenterPermisoDenegado)).all()) == 1
    client.put(f"/configuracion/roles/{rol['id']}", headers=_h(token),
               json={"nombre": "Mixto", "permisos": ["citas.ver"]})
    assert session.exec(select(UserCenterPermisoDenegado)).all() == []
    assert client.get("/configuracion/personal", headers=_h(token)).status_code == 200
    assert p["id"]


def test_sin_config_editar_no_se_editan_roles(client: TestClient, token: str, session: Session):
    rol = _rol(client, token, "Citas", ["citas.ver"])
    u = Usuario(nombre="Sin", email="sin@x.local", password_hash=__import__("infrastructure.security", fromlist=["x"]).hash_password("sin12345"))
    session.add(u); session.commit(); session.refresh(u)
    session.add(UserCenterRole(usuario_id=u.id, centro_id=1, rol_id=rol["id"]))
    session.add(UsuarioPeriodo(usuario_id=u.id, centro_id=1, orden=0, staff_tipo="RECEPCION", fecha_alta=date(2026, 1, 1)))
    session.commit()
    tok = client.post("/auth/login", json={"email": "sin@x.local", "password": "sin12345"}).json()["access_token"]
    assert client.post("/configuracion/roles", headers=_h(tok), json={"nombre": "Z", "permisos": []}).status_code == 403


def test_pestanas_aparecen_en_el_catalogo_de_areas(client: TestClient, token: str, session: Session):
    _asegura(session, ("pacientes.tab.ficha", "gestoria.tab.facturacion", "gestoria.tab.produccion"))
    d = client.get("/configuracion/roles", headers=_h(token)).json()
    ges = next(a for a in d["permiso_areas"] if a["key"] == "gestoria")
    assert [t["codigo"] for t in ges["tabs"]] == ["gestoria.tab.facturacion", "gestoria.tab.produccion"]
    assert all(not e["codigo"].startswith(("gestoria.tab", "pacientes.tab")) for e in d["permiso_extras"])


def test_limitar_pestanas_dentro_del_rol(client: TestClient, token: str, session: Session):
    _asegura(session, ("gestoria.tab.facturacion", "gestoria.tab.produccion"))
    rol = _rol(client, token, "Gestoría", ["gestoria.ver", "gestoria.tab.facturacion", "gestoria.tab.produccion"])
    p = _persona(client, token, rol["id"], ["gestoria.ver", "gestoria.tab.facturacion"], nombre="Solo fact").json()
    assert p["permisos"] == ["gestoria.tab.facturacion", "gestoria.ver"]     # sin la pestaña Producción
    r = client.put(f"/configuracion/personal/{p['id']}", headers=_h(token),
                   json={"nombre": "Solo fact", "permisos": ["gestoria.ver", "pacientes.ver"]})
    assert r.status_code == 400


def test_secciones_dentro_de_pestana_y_limite_por_persona(client: TestClient, token: str, session: Session):
    cods = ["gestoria.tab.facturacion", "gestoria.tab.facturacion.debehaber", "gestoria.tab.facturacion.facturas",
            "gestoria.tab.facturacion.pagos"]
    _asegura(session, cods)
    d = client.get("/configuracion/roles", headers=_h(token)).json()
    ges = next(a for a in d["permiso_areas"] if a["key"] == "gestoria")
    fac = next(t for t in ges["tabs"] if t["codigo"] == "gestoria.tab.facturacion")
    assert [x["codigo"].split(".")[-1] for x in fac["subs"]][:3] == ["debehaber", "facturas", "pagos"]
    assert all(not e["codigo"].startswith("gestoria.tab") for e in d["permiso_extras"])
    rol = _rol(client, token, "Asesoría 2", ["gestoria.ver"] + cods)
    p = _persona(client, token, rol["id"], ["gestoria.ver"] + cods[:3], nombre="Sin pagos").json()
    assert "gestoria.tab.facturacion.pagos" not in p["permisos"]
    assert "gestoria.tab.facturacion.facturas" in p["permisos"]
