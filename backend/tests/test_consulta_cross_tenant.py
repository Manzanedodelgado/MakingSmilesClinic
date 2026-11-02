"""guardar_soap / guardar_receta — regresión IDOR cross-tenant.

Antes del fix, ambas funciones creaban Cita/Soap/Receta con `paciente_id` tal cual venía
del path, sin comprobar que perteneciera a `centro_id` (el centro activo, resuelto por
get_current_centro a partir del JWT/cabecera X-Centro-Id — nunca del cuerpo de la petición).
Un usuario con acceso solo al Centro A podía escribir SOAP/recetas sobre un paciente del
Centro B con solo conocer su id numérico.
"""
from datetime import date

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from domain.models.clinico import Soap
from domain.models.core import Centro, Colaborador, Paciente
from domain.models.documentos import Receta, RecetaLinea, Talonario, TalonarioReceta
from domain.models.identidad import Permiso, Rol, RolePermiso, UsuarioPeriodo, UserCenterPermiso, UserCenterRole


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _dar_talonario(session: Session, centro_id: int, usuario_id: int) -> None:
    """Da de alta un colaborador (vinculado al usuario_id) con un talonario con 1 número
    libre — requisito real desde el fix de guardar_receta() (consume número oficial)."""
    from datetime import date as _date
    per = UsuarioPeriodo(usuario_id=usuario_id, centro_id=centro_id, orden=0, staff_tipo="DOCTOR",
                        fecha_alta=_date(2026, 1, 1))
    session.add(per); session.commit(); session.refresh(per)
    col = Colaborador(periodo_id=per.id)
    session.add(col); session.commit(); session.refresh(col)
    tal = Talonario(centro_id=centro_id, colaborador_id=col.id, numero_lote="TEST", total_numeros=5, activo=True)
    session.add(tal); session.commit(); session.refresh(tal)
    for i in range(5):
        session.add(TalonarioReceta(talonario_id=tal.id, numero=f"T{i}", cve=f"CVE{i}", usada=False))
    col.talonario_id = tal.id
    session.add(col); session.commit()


def _setup_dos_centros(session: Session, token_admin_id: int):
    """Centro A = 1 (ya sembrado). Centro B = nuevo. El admin (ya con acceso a A) recibe
    también acceso de administrador a B, para poder probar ambos con el mismo token
    cambiando solo la cabecera X-Centro-Id. Los permisos efectivos vienen de
    user_center_permisos (concesión directa), NO del rol — el rol solo da membresía."""
    centro_b = Centro(nombre="Clínica B (otro tenant)", codigo="CLB")
    session.add(centro_b); session.commit(); session.refresh(centro_b)

    rol_b = Rol(centro_id=centro_b.id, nombre="Administrador B")
    session.add(rol_b); session.commit(); session.refresh(rol_b)
    session.add(UserCenterRole(usuario_id=token_admin_id, centro_id=centro_b.id, rol_id=rol_b.id))
    for cod in ("pacientes.ver", "pacientes.editar"):
        p = session.exec(select(Permiso).where(Permiso.codigo == cod)).first()
        session.add(UserCenterPermiso(usuario_id=token_admin_id, centro_id=centro_b.id, permiso_id=p.id))
    session.commit()

    pac_a = Paciente(centro_id=1, nombre="Paciente", apellidos="Del Centro A")
    pac_b = Paciente(centro_id=centro_b.id, nombre="Paciente", apellidos="Del Centro B")
    session.add(pac_a); session.add(pac_b)
    session.commit(); session.refresh(pac_a); session.refresh(pac_b)
    return centro_b, pac_a, pac_b


def _admin_id(client: TestClient, token: str) -> int:
    me = client.get("/auth/me", headers=_auth(token)).json()
    return me["usuario_id"]


def _sin_filas_huerfanas(session: Session, pac_id: int) -> bool:
    from domain.models.core import Cita
    citas = session.exec(select(Cita).where(Cita.paciente_id == pac_id)).all()
    soaps = session.exec(select(Soap).where(Soap.paciente_id == pac_id)).all()
    recetas = session.exec(select(Receta).where(Receta.paciente_id == pac_id)).all()
    return not citas and not soaps and not recetas


def test_soap_centro_a_paciente_a_funciona(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, pac_a, _pac_b = _setup_dos_centros(session, admin_id)
    r = client.post(f"/pacientes/{pac_a.id}/consulta/soap", headers=_auth(token),
                    json={"subjetivo": "Dolor leve", "objetivo": "Sin hallazgos"})
    assert r.status_code == 201, r.text


def test_soap_centro_a_paciente_b_rechazado_y_sin_filas(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, _pac_a, pac_b = _setup_dos_centros(session, admin_id)
    # Header X-Centro-Id se omite → get_current_centro usa el único centro si hay uno solo;
    # como el admin ahora tiene 2 accesos, hay que fijarlo explícitamente en A.
    r = client.post(f"/pacientes/{pac_b.id}/consulta/soap",
                    headers={**_auth(token), "X-Centro-Id": "1"},
                    json={"subjetivo": "Intento cross-tenant"})
    assert r.status_code == 422, r.text
    assert _sin_filas_huerfanas(session, pac_b.id)


def test_soap_centro_b_paciente_b_funciona(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    centro_b, _pac_a, pac_b = _setup_dos_centros(session, admin_id)
    # El token original se emitió ANTES de tener acceso a B (accesos van dentro del JWT) —
    # hay que volver a loguear para que el nuevo acceso se refleje.
    tok_b = client.post("/auth/login", json={
        "email": "admin@makingsmiles.local", "password": "admin1234"}).json()["access_token"]
    r = client.post(f"/pacientes/{pac_b.id}/consulta/soap",
                    headers={**_auth(tok_b), "X-Centro-Id": str(centro_b.id)},
                    json={"subjetivo": "Nota legítima en su propio centro"})
    assert r.status_code == 201, r.text


def test_soap_paciente_inexistente_rechazado(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _setup_dos_centros(session, admin_id)
    r = client.post("/pacientes/999999/consulta/soap",
                    headers={**_auth(token), "X-Centro-Id": "1"},
                    json={"subjetivo": "x"})
    assert r.status_code == 422, r.text


def test_camino_centro_a_paciente_b_rechazado(client: TestClient, token: str, session: Session):
    """detectar_camino leía Paciente/Cita por id sin comprobar centro_id: un usuario del
    Centro A podía consultar el estado clínico (anamnesis/citas/previstos) de un paciente
    del Centro B con solo conocer su id numérico."""
    admin_id = _admin_id(client, token)
    _centro_b, _pac_a, pac_b = _setup_dos_centros(session, admin_id)
    r = client.get(f"/pacientes/{pac_b.id}/consulta/camino",
                   headers={**_auth(token), "X-Centro-Id": "1"})
    assert r.status_code == 404, r.text


def test_camino_centro_a_paciente_a_funciona(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, pac_a, _pac_b = _setup_dos_centros(session, admin_id)
    r = client.get(f"/pacientes/{pac_a.id}/consulta/camino", headers={**_auth(token), "X-Centro-Id": "1"})
    assert r.status_code == 200, r.text
    assert "camino" in r.json()


def test_soap_sin_permiso_editar_da_403(client: TestClient, session: Session):
    from datetime import date as _date
    from domain.models.identidad import Usuario, UsuarioPeriodo
    from infrastructure.security import hash_password

    rol_ver = Rol(centro_id=1, nombre="Solo lectura pacientes")
    session.add(rol_ver); session.commit(); session.refresh(rol_ver)
    user = Usuario(email="solover@demo.local", nombre="Solo Ver",
                   password_hash=hash_password("solover1234"))
    session.add(user); session.commit(); session.refresh(user)
    session.add(UserCenterRole(usuario_id=user.id, centro_id=1, rol_id=rol_ver.id))
    ver = session.exec(select(Permiso).where(Permiso.codigo == "pacientes.ver")).first()
    session.add(UserCenterPermiso(usuario_id=user.id, centro_id=1, permiso_id=ver.id))
    session.add(UsuarioPeriodo(usuario_id=user.id, centro_id=1, orden=0, staff_tipo="RECEPCION",
                               fecha_alta=_date(2026, 1, 1)))
    session.commit()

    pac_a = Paciente(centro_id=1, nombre="Paciente", apellidos="Solo Lectura")
    session.add(pac_a); session.commit(); session.refresh(pac_a)

    tok = client.post("/auth/login", json={
        "email": "solover@demo.local", "password": "solover1234",
    }).json()["access_token"]
    r = client.post(f"/pacientes/{pac_a.id}/consulta/soap", headers=_auth(tok),
                    json={"subjetivo": "no debería poder"})
    assert r.status_code == 403


# ─────────────────────────── mismo bloque para guardar_receta ───────────────────────────
RECETA_BODY = {"medicamentos": [{"medicamento": "Amoxicilina 500mg", "posologia": "1 cada 8h"}]}


def test_receta_centro_a_paciente_a_funciona(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, pac_a, _pac_b = _setup_dos_centros(session, admin_id)
    _dar_talonario(session, 1, admin_id)
    r = client.post(f"/pacientes/{pac_a.id}/consulta/receta", headers=_auth(token), json=RECETA_BODY)
    assert r.status_code == 201, r.text


def test_receta_centro_a_paciente_b_rechazado_y_sin_filas(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, _pac_a, pac_b = _setup_dos_centros(session, admin_id)
    r = client.post(f"/pacientes/{pac_b.id}/consulta/receta",
                    headers={**_auth(token), "X-Centro-Id": "1"}, json=RECETA_BODY)
    assert r.status_code == 422, r.text
    assert _sin_filas_huerfanas(session, pac_b.id)
    assert session.exec(select(RecetaLinea)).all() == []


def test_receta_centro_b_paciente_b_funciona(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    centro_b, _pac_a, pac_b = _setup_dos_centros(session, admin_id)
    _dar_talonario(session, centro_b.id, admin_id)
    tok_b = client.post("/auth/login", json={
        "email": "admin@makingsmiles.local", "password": "admin1234"}).json()["access_token"]
    r = client.post(f"/pacientes/{pac_b.id}/consulta/receta",
                    headers={**_auth(tok_b), "X-Centro-Id": str(centro_b.id)}, json=RECETA_BODY)
    assert r.status_code == 201, r.text


def test_receta_paciente_inexistente_rechazado(client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _setup_dos_centros(session, admin_id)
    r = client.post("/pacientes/999999/consulta/receta",
                    headers={**_auth(token), "X-Centro-Id": "1"}, json=RECETA_BODY)
    assert r.status_code == 422, r.text


def test_receta_sin_talonario_rechazada(client: TestClient, token: str, session: Session):
    """Doctor sin talonario subido → rechazado, no crea una receta 'informal' sin número
    oficial (regresión del fix de consumo de talonario en guardar_receta())."""
    admin_id = _admin_id(client, token)
    _centro_b, pac_a, _pac_b = _setup_dos_centros(session, admin_id)
    # Sin _dar_talonario(): el admin no tiene colaborador/talonario en este test.
    r = client.post(f"/pacientes/{pac_a.id}/consulta/receta", headers=_auth(token), json=RECETA_BODY)
    assert r.status_code == 422, r.text


def test_receta_consume_numeros_de_talonario_en_orden_y_rechaza_al_agotarse(
        client: TestClient, token: str, session: Session):
    admin_id = _admin_id(client, token)
    _centro_b, pac_a, _pac_b = _setup_dos_centros(session, admin_id)
    _dar_talonario(session, 1, admin_id)   # 5 números libres

    ids_usados = []
    for _ in range(5):
        r = client.post(f"/pacientes/{pac_a.id}/consulta/receta", headers=_auth(token), json=RECETA_BODY)
        assert r.status_code == 201, r.text
        rec = session.get(Receta, r.json()["receta_id"])
        assert rec.talonario_receta_id is not None
        assert rec.cve is not None
        ids_usados.append(rec.talonario_receta_id)

    assert len(set(ids_usados)) == 5   # cada receta consumió un número distinto

    # El sexto intento: talonario agotado → rechazado
    r6 = client.post(f"/pacientes/{pac_a.id}/consulta/receta", headers=_auth(token), json=RECETA_BODY)
    assert r6.status_code == 422, r6.text
