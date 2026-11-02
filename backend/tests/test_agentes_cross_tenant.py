"""agentes_router → POST /agentes/victor/consulta/escuchar — regresión IDOR cross-tenant.

Antes del fix, VictorConsultaService.escuchar() (entonces AuraService, renombrado al pasar
la consulta de Aura a Victor) creaba una Transcripcion (audio clínico transcrito +
SOAP extraído) con cita_id/paciente_id tal cual venían del form-data, sin comprobar que el
paciente perteneciera a centro_id NI que la cita perteneciera a ESE paciente. Mismo patrón
que guardar_soap/guardar_receta (consulta_router) y crear_cita/editar_cita (agenda_router),
pero aquí intervienen DOS relaciones que verificar: centro→paciente y centro→paciente→cita.
"""
from datetime import date

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from domain.models.core import Centro, Cita, Paciente
from domain.models.ia import Transcripcion
from domain.models.identidad import Permiso, Rol, UserCenterPermiso, UserCenterRole


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin_id(client: TestClient, token: str) -> int:
    return client.get("/auth/me", headers=_auth(token)).json()["usuario_id"]


def _setup_dos_centros(session: Session, admin_id: int):
    """Centro A = 1 (ya sembrado). Centro B = nuevo, con paciente y cita propios."""
    centro_b = Centro(nombre="Clínica B (otro tenant)", codigo="CLB-AURA")
    session.add(centro_b); session.commit(); session.refresh(centro_b)

    rol_b = Rol(centro_id=centro_b.id, nombre="Administrador B")
    session.add(rol_b); session.commit(); session.refresh(rol_b)
    session.add(UserCenterRole(usuario_id=admin_id, centro_id=centro_b.id, rol_id=rol_b.id))
    for cod in ("pacientes.editar", "pacientes.ver"):
        p = session.exec(select(Permiso).where(Permiso.codigo == cod)).first()
        session.add(UserCenterPermiso(usuario_id=admin_id, centro_id=centro_b.id, permiso_id=p.id))
    session.commit()

    pac_a = Paciente(centro_id=1, nombre="Paciente", apellidos="Del Centro A (aura)")
    pac_b = Paciente(centro_id=centro_b.id, nombre="Paciente", apellidos="Del Centro B (aura)")
    session.add(pac_a); session.add(pac_b)
    session.commit(); session.refresh(pac_a); session.refresh(pac_b)

    cita_a = Cita(centro_id=1, paciente_id=pac_a.id, fecha=date.today(), hora="10:00")
    cita_b = Cita(centro_id=centro_b.id, paciente_id=pac_b.id, fecha=date.today(), hora="10:00")
    session.add(cita_a); session.add(cita_b)
    session.commit(); session.refresh(cita_a); session.refresh(cita_b)

    return centro_b, pac_a, pac_b, cita_a, cita_b


def _n_transcripciones(session: Session) -> int:
    return len(session.exec(select(Transcripcion)).all())


def _escuchar(client: TestClient, token: str, centro_header: str, cita_id: int, paciente_id: int):
    return client.post(
        "/agentes/victor/consulta/escuchar",
        headers={**_auth(token), "X-Centro-Id": centro_header},
        data={"cita_id": str(cita_id), "paciente_id": str(paciente_id)},
        files={"audio": ("consulta.wav", b"fake-audio-bytes", "audio/wav")},
    )


def test_escuchar_centro_a_paciente_a_cita_a_pasa_validacion(client: TestClient, token: str, session: Session):
    """No hay motor STT configurado en el entorno de test, así que no llega a transcribir
    de verdad — pero SÍ debe pasar la validación de tenant (no puede rechazar por
    'Paciente no encontrado' ni 'Cita no encontrada')."""
    admin_id = _admin_id(client, token)
    _centro_b, pac_a, _pac_b, cita_a, _cita_b = _setup_dos_centros(session, admin_id)
    r = _escuchar(client, token, "1", cita_a.id, pac_a.id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["motivo"] not in ("Paciente no encontrado", "Cita no encontrada")


def test_escuchar_centro_a_paciente_b_rechazado_y_sin_transcripciones(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, _pac_a, pac_b, _cita_a, cita_b = _setup_dos_centros(session, admin_id)
    n_antes = _n_transcripciones(session)
    # cita_b/pac_b son del centro B; se llama en el centro A.
    r = _escuchar(client, token, "1", cita_b.id, pac_b.id)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": False, "motivo": "Paciente no encontrado"}
    assert _n_transcripciones(session) == n_antes


def test_escuchar_centro_b_paciente_b_pasa_validacion(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    centro_b, _pac_a, pac_b, _cita_a, cita_b = _setup_dos_centros(session, admin_id)
    tok_b = client.post("/auth/login", json={
        "email": "admin@makingsmiles.local", "password": "admin1234"}).json()["access_token"]
    r = _escuchar(client, tok_b, str(centro_b.id), cita_b.id, pac_b.id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["motivo"] not in ("Paciente no encontrado", "Cita no encontrada")


def test_escuchar_paciente_inexistente_rechazado_y_sin_transcripciones(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, _pac_a, _pac_b, cita_a, _cita_b = _setup_dos_centros(session, admin_id)
    n_antes = _n_transcripciones(session)
    r = _escuchar(client, token, "1", cita_a.id, 999999)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": False, "motivo": "Paciente no encontrado"}
    assert _n_transcripciones(session) == n_antes


def test_escuchar_sin_permiso_editar_da_403(client: TestClient, session: Session):
    from domain.models.identidad import Usuario, UsuarioPeriodo
    from infrastructure.security import hash_password

    rol_ver = Rol(centro_id=1, nombre="Solo lectura aura")
    session.add(rol_ver); session.commit(); session.refresh(rol_ver)
    user = Usuario(email="soloveraura@demo.local", nombre="Solo Ver Aura",
                   password_hash=hash_password("solover1234"))
    session.add(user); session.commit(); session.refresh(user)
    session.add(UserCenterRole(usuario_id=user.id, centro_id=1, rol_id=rol_ver.id))
    ver = session.exec(select(Permiso).where(Permiso.codigo == "pacientes.ver")).first()
    session.add(UserCenterPermiso(usuario_id=user.id, centro_id=1, permiso_id=ver.id))
    session.add(UsuarioPeriodo(usuario_id=user.id, centro_id=1, orden=0, staff_tipo="RECEPCION",
                               fecha_alta=date(2026, 1, 1)))
    session.commit()

    pac_a = Paciente(centro_id=1, nombre="Paciente", apellidos="Sin Permiso Aura")
    session.add(pac_a); session.commit(); session.refresh(pac_a)
    cita_a = Cita(centro_id=1, paciente_id=pac_a.id, fecha=date.today(), hora="10:00")
    session.add(cita_a); session.commit(); session.refresh(cita_a)

    tok = client.post("/auth/login", json={
        "email": "soloveraura@demo.local", "password": "solover1234"}).json()["access_token"]
    r = _escuchar(client, tok, "1", cita_a.id, pac_a.id)
    assert r.status_code == 403


def test_escuchar_paciente_valido_pero_cita_de_otro_paciente_rechazado_y_sin_transcripciones(
        client: TestClient, token: str, session: Session):
    """Caso clave: paciente_id SÍ pertenece al centro, pero cita_id pertenece a OTRO paciente
    (incluso de otro centro) — valida la relación completa centro→paciente→cita, no solo
    que el paciente exista en el centro."""
    admin_id = _admin_id(client, token)
    _centro_b, pac_a, _pac_b, _cita_a, cita_b = _setup_dos_centros(session, admin_id)
    n_antes = _n_transcripciones(session)
    # pac_a es válido en el centro 1, pero cita_b pertenece a pac_b/centro B.
    r = _escuchar(client, token, "1", cita_b.id, pac_a.id)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": False, "motivo": "Cita no encontrada"}
    assert _n_transcripciones(session) == n_antes
