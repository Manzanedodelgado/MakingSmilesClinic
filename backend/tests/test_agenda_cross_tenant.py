"""crear_cita / editar_cita (agenda) — regresión IDOR cross-tenant.

Antes del fix, CitaIn.paciente_id se volcaba directo en la Cita (crear_cita) o se
reasignaba con setattr (editar_cita) sin comprobar que ese paciente perteneciera al
centro_id autenticado. Mismo patrón que guardar_soap/guardar_receta.
"""
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from domain.models.core import Centro, Cita, Paciente
from domain.models.identidad import Permiso, Rol, UserCenterPermiso, UserCenterRole


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin_id(client: TestClient, token: str) -> int:
    return client.get("/auth/me", headers=_auth(token)).json()["usuario_id"]


def _setup_dos_centros(session: Session, admin_id: int):
    centro_b = Centro(nombre="Clínica B (otro tenant)", codigo="CLB-AG")
    session.add(centro_b); session.commit(); session.refresh(centro_b)

    rol_b = Rol(centro_id=centro_b.id, nombre="Administrador B")
    session.add(rol_b); session.commit(); session.refresh(rol_b)
    session.add(UserCenterRole(usuario_id=admin_id, centro_id=centro_b.id, rol_id=rol_b.id))
    for cod in ("citas.ver", "citas.editar", "pacientes.ver"):
        p = session.exec(select(Permiso).where(Permiso.codigo == cod)).first()
        session.add(UserCenterPermiso(usuario_id=admin_id, centro_id=centro_b.id, permiso_id=p.id))
    session.commit()

    pac_a = Paciente(centro_id=1, nombre="Paciente", apellidos="Del Centro A (agenda)")
    pac_b = Paciente(centro_id=centro_b.id, nombre="Paciente", apellidos="Del Centro B (agenda)")
    session.add(pac_a); session.add(pac_b)
    session.commit(); session.refresh(pac_a); session.refresh(pac_b)
    return centro_b, pac_a, pac_b


def _n_citas(session: Session) -> int:
    return len(session.exec(select(Cita)).all())


CITA_BODY = {"fecha": "2026-10-01", "hora": "10:00"}


def test_crear_cita_centro_a_paciente_a_funciona(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, pac_a, _pac_b = _setup_dos_centros(session, admin_id)
    r = client.post("/agenda/citas", headers={**_auth(token), "X-Centro-Id": "1"},
                    json={**CITA_BODY, "paciente_id": pac_a.id})
    assert r.status_code == 201, r.text


def test_crear_cita_centro_a_paciente_b_rechazado_y_sin_filas(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, _pac_a, pac_b = _setup_dos_centros(session, admin_id)
    n_antes = _n_citas(session)
    r = client.post("/agenda/citas", headers={**_auth(token), "X-Centro-Id": "1"},
                    json={**CITA_BODY, "paciente_id": pac_b.id})
    assert r.status_code == 422, r.text
    assert _n_citas(session) == n_antes


def test_crear_cita_centro_b_paciente_b_funciona(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    centro_b, _pac_a, pac_b = _setup_dos_centros(session, admin_id)
    tok_b = client.post("/auth/login", json={
        "email": "admin@makingsmiles.local", "password": "admin1234"}).json()["access_token"]
    r = client.post("/agenda/citas", headers={**_auth(tok_b), "X-Centro-Id": str(centro_b.id)},
                    json={**CITA_BODY, "paciente_id": pac_b.id})
    assert r.status_code == 201, r.text


def test_crear_cita_paciente_inexistente_rechazado(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _setup_dos_centros(session, admin_id)
    r = client.post("/agenda/citas", headers={**_auth(token), "X-Centro-Id": "1"},
                    json={**CITA_BODY, "paciente_id": 999999})
    assert r.status_code == 422, r.text


def test_crear_cita_sin_permiso_editar_da_403(client: TestClient, session: Session):
    from datetime import date as _date
    from domain.models.identidad import Usuario, UsuarioPeriodo
    from infrastructure.security import hash_password

    rol_ver = Rol(centro_id=1, nombre="Solo lectura agenda")
    session.add(rol_ver); session.commit(); session.refresh(rol_ver)
    user = Usuario(email="soloveragenda@demo.local", nombre="Solo Ver Agenda",
                   password_hash=hash_password("solover1234"))
    session.add(user); session.commit(); session.refresh(user)
    session.add(UserCenterRole(usuario_id=user.id, centro_id=1, rol_id=rol_ver.id))
    ver = session.exec(select(Permiso).where(Permiso.codigo == "citas.ver")).first()
    session.add(UserCenterPermiso(usuario_id=user.id, centro_id=1, permiso_id=ver.id))
    session.add(UsuarioPeriodo(usuario_id=user.id, centro_id=1, orden=0, staff_tipo="RECEPCION",
                               fecha_alta=_date(2026, 1, 1)))
    session.commit()

    tok = client.post("/auth/login", json={
        "email": "soloveragenda@demo.local", "password": "solover1234"}).json()["access_token"]
    r = client.post("/agenda/citas", headers=_auth(tok), json=CITA_BODY)
    assert r.status_code == 403


def test_editar_cita_reasignar_a_paciente_b_rechazado_y_conserva_paciente_original(
        client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, pac_a, pac_b = _setup_dos_centros(session, admin_id)
    creada = client.post("/agenda/citas", headers={**_auth(token), "X-Centro-Id": "1"},
                         json={**CITA_BODY, "paciente_id": pac_a.id})
    assert creada.status_code == 201, creada.text
    cita_id = creada.json()["id"]

    r = client.put(f"/agenda/citas/{cita_id}", headers={**_auth(token), "X-Centro-Id": "1"},
                   json={**CITA_BODY, "paciente_id": pac_b.id})
    assert r.status_code == 422, r.text

    session.expire_all()
    cita = session.get(Cita, cita_id)
    assert cita.paciente_id == pac_a.id   # conserva el paciente original, no se reasignó
