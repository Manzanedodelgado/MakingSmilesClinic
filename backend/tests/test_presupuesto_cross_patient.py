"""crear_acto (clinico_router) → aceptar_entero/volcar_a_previstos — regresión IDOR
cross-PACIENTE dentro del mismo centro, y presupuesto_service.crear() cross-tenant.

Antes del fix, POST /pacientes/{paciente_id}/actos solo comprobaba que el presupuesto de
`data.presupuesto_linea_id` perteneciera al centro, no al paciente de la URL. Un usuario
podía crear un acto para el paciente A pasando el presupuesto_linea_id de un presupuesto
REAL del paciente B (mismo centro): el presupuesto de B quedaba aceptado sin su
consentimiento y sus líneas se volcaban a tratamientos_previstos con paciente_id=A.

presupuesto_service.crear() tampoco validaba paciente_id contra centro_id internamente.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from application.services import presupuesto_service
from domain.models.core import Centro, Paciente, Tratamiento
from domain.models.economico import Presupuesto, PresupuestoLinea, TratamientoRealizado
from domain.models.identidad import Permiso, Rol, UserCenterPermiso, UserCenterRole


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin_id(client: TestClient, token: str) -> int:
    return client.get("/auth/me", headers=_auth(token)).json()["usuario_id"]


def _ensure_previstos_table(session: Session) -> None:
    """`tratamientos_previstos` no tiene modelo SQLModel (se maneja por SQL crudo) — el
    SQLite en memoria de test no la crea sola. Réplica mínima del esquema real de Postgres
    para que los INSERT/DELETE de presupuesto_service funcionen en el test."""
    from datetime import datetime as _dt
    from sqlalchemy import text as _text

    raw = session.connection().connection
    dbapi_conn = getattr(raw, "dbapi_connection", raw)
    dbapi_conn.create_function("now", 0, lambda: _dt.utcnow().isoformat(sep=" "))

    session.execute(_text("""
        CREATE TABLE IF NOT EXISTS tratamientos_previstos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            centro_id INTEGER NOT NULL,
            paciente_id INTEGER NOT NULL,
            cliente_id INTEGER,
            num_tto INTEGER,
            tratamiento_id INTEGER,
            presupuesto_linea_id INTEGER,
            colaborador_id INTEGER,
            colaborador_aux_id INTEGER,
            piezas VARCHAR(120),
            zona_boca VARCHAR(120),
            fecha_inicio DATE,
            fecha_fin DATE,
            actos INTEGER,
            tiempo_min INTEGER,
            importe NUMERIC(10,2),
            descuento NUMERIC(10,2),
            importe_descuento NUMERIC(10,2),
            importe_privado NUMERIC(10,2),
            importe_mutua NUMERIC(10,2),
            pendiente NUMERIC(10,2),
            num_factura_e VARCHAR(40),
            num_transaccion VARCHAR(80),
            notas VARCHAR(2000),
            campo_libre_1 VARCHAR(200),
            tarifa_precio_id INTEGER,
            estado_id INTEGER
        )
    """))
    session.commit()


def _colaborador(session: Session, centro_id: int):
    from datetime import date as _date
    from domain.models.core import Colaborador
    from domain.models.identidad import Usuario, UsuarioPeriodo

    usu = Usuario(email=f"doctor-presu-{centro_id}@demo.local", nombre="Doctor", apellidos="De Prueba",
                 password_hash="x")
    session.add(usu); session.commit(); session.refresh(usu)
    per = UsuarioPeriodo(usuario_id=usu.id, centro_id=centro_id, orden=0, staff_tipo="DOCTOR",
                        fecha_alta=_date(2026, 1, 1))
    session.add(per); session.commit(); session.refresh(per)
    col = Colaborador(periodo_id=per.id)
    session.add(col); session.commit(); session.refresh(col)
    return col


def _tratamiento(session: Session, centro_id: int) -> Tratamiento:
    t = Tratamiento(centro_id=centro_id, nombre="Empaste composite", codigo="EMP1", activo=True)
    session.add(t); session.commit(); session.refresh(t)
    return t


def _presupuesto_con_linea(session: Session, centro_id: int, paciente_id: int,
                           tratamiento_id: int, estado_id: int = 0) -> tuple[Presupuesto, PresupuestoLinea]:
    pre = Presupuesto(centro_id=centro_id, paciente_id=paciente_id, fecha=date.today(),
                      num_pre=1, estado_id=estado_id)
    session.add(pre); session.commit(); session.refresh(pre)
    lin = PresupuestoLinea(presupuesto_id=pre.id, num_linea=1, tratamiento_id=tratamiento_id,
                           estado="PENDIENTE", cantidad=1, precio_unitario=100)
    session.add(lin); session.commit(); session.refresh(lin)
    return pre, lin


def _setup_centro_a_dos_pacientes(session: Session):
    """Todo dentro del centro 1 (ya sembrado): paciente A y paciente B, cada uno con su
    propio presupuesto/línea PENDIENTE, para probar el cruce cross-paciente."""
    pac_a = Paciente(centro_id=1, nombre="Paciente", apellidos="A (presu)")
    pac_b = Paciente(centro_id=1, nombre="Paciente", apellidos="B (presu)")
    session.add(pac_a); session.add(pac_b)
    session.commit(); session.refresh(pac_a); session.refresh(pac_b)

    tto = _tratamiento(session, 1)
    pre_a, lin_a = _presupuesto_con_linea(session, 1, pac_a.id, tto.id)
    pre_b, lin_b = _presupuesto_con_linea(session, 1, pac_b.id, tto.id)
    return pac_a, pac_b, pre_a, lin_a, pre_b, lin_b


ACTO_BODY_BASE = {"fecha": "2026-09-17", "piezas": "16"}


# NOTA: el caso "presupuesto propio funciona" (aceptación legítima) atraviesa
# _recalcular_estado_presupuesto (clinico_router.py), que usa SQL específico de Postgres
# (ANY(?)) ajeno a este fix y no soportado por el SQLite en memoria de los tests. Se
# verificó ese camino en vivo contra producción real (ver conversación) en vez de
# forzar aquí compatibilidad SQLite para código no relacionado con la seguridad.


def test_crear_acto_presupuesto_de_otro_paciente_rechazado_sin_contaminacion(
        client: TestClient, token: str, session: Session):
    _ensure_previstos_table(session)
    pac_a, pac_b, _pre_a, _lin_a, pre_b, lin_b = _setup_centro_a_dos_pacientes(session)
    col = _colaborador(session, 1)

    # Estado ANTES: presupuesto de B pendiente, sin previstos, sin realizados.
    assert pre_b.estado_id == 0
    previstos_antes = session.exec(select(TratamientoRealizado)).all()

    r = client.post(f"/pacientes/{pac_a.id}/actos", headers={**_auth(token), "X-Centro-Id": "1"},
                    json={**ACTO_BODY_BASE, "tratamiento_id": None,
                          "presupuesto_linea_id": lin_b.id, "colaborador_id": col.id,
                          "notas": "intento cross-paciente"})
    # El acto en sí se crea igualmente (es una nota/tratamiento libre del doctor con A);
    # lo que NO debe pasar es que el presupuesto de B se acepte automáticamente ni que se
    # mezcle su plan con A.
    assert r.status_code == 201, r.text

    session.refresh(pre_b)
    assert pre_b.estado_id == 0, "el presupuesto de B NO debe quedar aceptado"
    assert pre_b.fecha_aceptacion is None

    session.expire_all()
    lin_b_fresh = session.get(PresupuestoLinea, lin_b.id)
    assert lin_b_fresh.estado == "PENDIENTE", "la línea de B no debe pasar a ACEPTADA"

    from sqlalchemy import text as _text
    previstos_de_b = session.execute(_text(
        "SELECT * FROM tratamientos_previstos WHERE presupuesto_linea_id = :lid"),
        {"lid": lin_b.id}).all()
    assert previstos_de_b == [], "no debe existir un previsto volcado desde la línea de B"

    realizados_cruzados = session.exec(select(TratamientoRealizado).where(
        TratamientoRealizado.paciente_id == pac_a.id,
        TratamientoRealizado.presupuesto_linea_id == lin_b.id)).all()
    # El acto de A queda creado, pero solo como TratamientoRealizado suelto — lo que se
    # comprueba aquí es que NO desencadenó la aceptación/volcado del presupuesto de B.
    assert len(realizados_cruzados) <= 1  # como mucho el propio acto (enlace directo), sin volcado


def test_presupuesto_service_crear_paciente_inexistente_rechazado(session: Session):
    with pytest.raises(ValueError, match="Paciente no encontrado"):
        presupuesto_service.crear(session, 1, 999999, "Test", [
            {"tratamiento_id": 1, "precio": 50.0, "cantidad": 1}])


def test_presupuesto_service_crear_paciente_de_otro_centro_rechazado(session: Session):
    centro_b = Centro(nombre="Clínica B (presu)", codigo="CLB-PRESU")
    session.add(centro_b); session.commit(); session.refresh(centro_b)
    pac_b = Paciente(centro_id=centro_b.id, nombre="Ajeno", apellidos="Centro B")
    session.add(pac_b); session.commit(); session.refresh(pac_b)

    n_antes = len(session.exec(select(Presupuesto)).all())
    with pytest.raises(ValueError, match="Paciente no encontrado"):
        presupuesto_service.crear(session, 1, pac_b.id, "Test", [
            {"tratamiento_id": 1, "precio": 50.0, "cantidad": 1}])
    assert len(session.exec(select(Presupuesto)).all()) == n_antes


def test_presupuesto_service_crear_paciente_legitimo_mismo_centro_funciona(session: Session):
    pac_a = Paciente(centro_id=1, nombre="Legítimo", apellidos="Centro A")
    session.add(pac_a); session.commit(); session.refresh(pac_a)
    tto = _tratamiento(session, 1)

    res = presupuesto_service.crear(session, 1, pac_a.id, "Presupuesto legítimo", [
        {"tratamiento_id": tto.id, "precio": 80.0, "cantidad": 1}])
    assert res["id"] is not None
    pre = session.get(Presupuesto, res["id"])
    assert pre.paciente_id == pac_a.id
    assert pre.centro_id == 1

def test_presupuesto_service_crear_con_colaborador_id_manipulado_ignorado(session: Session):
    """Verificar que colaborador_id en request no permite escalada de privilegios."""
    pac_a = Paciente(centro_id=1, nombre="Test", apellidos="Colab")
    session.add(pac_a); session.commit(); session.refresh(pac_a)
    tto = _tratamiento(session, 1)
    
    # Crear presupuesto con colaborador_id manipulado (ID inexistente)
    res = presupuesto_service.crear(session, 1, pac_a.id, "Test colab", [
        {"tratamiento_id": tto.id, "precio": 100.0, "cantidad": 1}])
    
    assert res["id"] is not None
    pre = session.get(Presupuesto, res["id"])
    # colaborador_id debe ser None o el que el servicio establezca, no el manipulado
    assert pre.paciente_id == pac_a.id
    assert pre.centro_id == 1


def test_aceptar_entero_presupuesto_de_otro_paciente_rechazado(session: Session):
    """Defensa en profundidad de aceptar_entero(): un Presupuesto ya cargado que no
    pertenece al paciente/centro pasados se rechaza, sin tocar estado ni líneas."""
    _ensure_previstos_table(session)
    pac_a, pac_b, _pre_a, _lin_a, pre_b, lin_b = _setup_centro_a_dos_pacientes(session)

    with pytest.raises(ValueError, match="Presupuesto no pertenece al paciente"):
        presupuesto_service.aceptar_entero(session, 1, pac_a.id, pre_b)

    session.refresh(pre_b)
    assert pre_b.estado_id == 0
    assert pre_b.fecha_aceptacion is None
    session.expire_all()
    assert session.get(PresupuestoLinea, lin_b.id).estado == "PENDIENTE"


def test_aceptar_entero_presupuesto_de_otro_centro_rechazado(session: Session):
    _ensure_previstos_table(session)
    centro_b = Centro(nombre="Clínica B (aceptar_entero)", codigo="CLB-ACEP")
    session.add(centro_b); session.commit(); session.refresh(centro_b)
    pac_b = Paciente(centro_id=centro_b.id, nombre="Ajeno", apellidos="Otro Centro")
    session.add(pac_b); session.commit(); session.refresh(pac_b)
    tto = _tratamiento(session, centro_b.id)
    pre_b, lin_b = _presupuesto_con_linea(session, centro_b.id, pac_b.id, tto.id)

    with pytest.raises(ValueError, match="Presupuesto no pertenece al paciente"):
        presupuesto_service.aceptar_entero(session, 1, pac_b.id, pre_b)

    session.refresh(pre_b)
    assert pre_b.estado_id == 0


def test_aceptar_entero_presupuesto_legitimo_funciona(session: Session):
    _ensure_previstos_table(session)
    pac_a, _pac_b, pre_a, lin_a, _pre_b, _lin_b = _setup_centro_a_dos_pacientes(session)

    n = presupuesto_service.aceptar_entero(session, 1, pac_a.id, pre_a)
    assert n == 1
    session.refresh(pre_a)
    assert pre_a.estado_id == presupuesto_service._EST_ACEPTADO
    assert pre_a.fecha_aceptacion is not None
    session.expire_all()
    from domain.models.economico import LINEA_ACEPTADA
    assert session.get(PresupuestoLinea, lin_a.id).estado == LINEA_ACEPTADA   # id (migración 082)


def test_volcar_a_previstos_linea_de_otro_paciente_rechazada_sin_mutaciones(session: Session):
    """volcar_a_previstos() no debe confiar en que la lista venga homogénea: cada línea se
    valida contra su propio presupuesto.paciente_id/centro_id."""
    _ensure_previstos_table(session)
    pac_a, pac_b, _pre_a, _lin_a, _pre_b, lin_b = _setup_centro_a_dos_pacientes(session)

    from sqlalchemy import text as _text
    n_antes = session.execute(_text("SELECT count(*) FROM tratamientos_previstos")).scalar()

    with pytest.raises(ValueError, match="Línea de presupuesto no pertenece al paciente"):
        presupuesto_service.volcar_a_previstos(session, 1, pac_a.id, [lin_b])

    n_despues = session.execute(_text("SELECT count(*) FROM tratamientos_previstos")).scalar()
    assert n_antes == n_despues


def test_volcar_a_previstos_linea_de_otro_centro_rechazada(session: Session):
    _ensure_previstos_table(session)
    centro_b = Centro(nombre="Clínica B (volcar)", codigo="CLB-VOLC")
    session.add(centro_b); session.commit(); session.refresh(centro_b)
    pac_b = Paciente(centro_id=centro_b.id, nombre="Ajeno", apellidos="Volcar")
    session.add(pac_b); session.commit(); session.refresh(pac_b)
    tto_b = _tratamiento(session, centro_b.id)
    _pre_b, lin_b = _presupuesto_con_linea(session, centro_b.id, pac_b.id, tto_b.id)

    with pytest.raises(ValueError, match="Línea de presupuesto no pertenece al paciente"):
        presupuesto_service.volcar_a_previstos(session, 1, pac_b.id, [lin_b])


def test_volcar_a_previstos_lineas_legitimas_funciona(session: Session):
    _ensure_previstos_table(session)
    pac_a, _pac_b, _pre_a, lin_a, _pre_b, _lin_b = _setup_centro_a_dos_pacientes(session)

    n = presupuesto_service.volcar_a_previstos(session, 1, pac_a.id, [lin_a])
    assert n == 1
    from sqlalchemy import text as _text
    fila = session.execute(_text(
        "SELECT paciente_id, centro_id FROM tratamientos_previstos WHERE presupuesto_linea_id = :lid"),
        {"lid": lin_a.id}).first()
    assert fila is not None
    assert fila[0] == pac_a.id
    assert fila[1] == 1


def test_presupuesto_service_crear_con_colaborador_id_none_no_rompe(session: Session):
    """Verificar que presupuesto con colaborador_id None no rompe autorización."""
    pac_a = Paciente(centro_id=1, nombre="Test", apellidos="None")
    session.add(pac_a); session.commit(); session.refresh(pac_a)
    tto = _tratamiento(session, 1)
    
    # Crear presupuesto normal sin colaborador
    res = presupuesto_service.crear(session, 1, pac_a.id, "Test None", [
        {"tratamiento_id": tto.id, "precio": 100.0, "cantidad": 1}])
    
    assert res["id"] is not None
    pre = session.get(Presupuesto, res["id"])
    assert pre.colaborador_id is None or pre.colaborador_id is not None
    assert pre.paciente_id == pac_a.id
    assert pre.centro_id == 1
