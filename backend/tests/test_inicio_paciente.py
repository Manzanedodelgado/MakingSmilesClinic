"""INICIO · el paciente de agenda: citas, automatizaciones y flujo de WhatsApp en una llamada.

Cada sección respeta su permiso y nada cruza de centro.
"""
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from application.services.comunicacion_service import ComunicacionService
from application.services.inicio_paciente_service import InicioPacienteService
from domain.models.agenda import EstadoCita, Gabinete, TipoCita
from domain.models.comunicacion import Conversacion, EnvioAutomatico
from domain.models.core import Centro, Cita, Colaborador, Paciente
from domain.models.identidad import Usuario, UsuarioPeriodo

TODO = {"citas.ver", "comunicacion.ver"}


def _add(session: Session, *objs):
    for o in objs:
        session.add(o)
    session.commit()
    for o in objs:
        session.refresh(o)
    return objs


def _otro_centro(session: Session) -> int:
    c, = _add(session, Centro(nombre="Otro"))
    return c.id


def test_paciente_de_otro_centro_no_existe(session: Session):
    otro = _otro_centro(session)
    pac, = _add(session, Paciente(centro_id=otro, nombre="Ajeno"))
    assert InicioPacienteService(session, 1, TODO).resumen(pac.id) is None
    assert InicioPacienteService(session, 1, TODO).resumen(999999) is None


def test_citas_proximas_y_pasadas_sin_anuladas_con_doctor(session: Session):
    u, = _add(session, Usuario(email="ana@t.es", nombre="Ana", apellidos="Doc", password_hash="x"))
    per, = _add(session, UsuarioPeriodo(usuario_id=u.id, centro_id=1, fecha_alta=date(2020, 1, 1)))
    col, = _add(session, Colaborador(periodo_id=per.id, activo=True))
    pac, otro_pac, conf, anul, gab, tipo = _add(
        session,
        Paciente(centro_id=1, nombre="Juan", apellidos="Prueba"),
        Paciente(centro_id=1, nombre="Otro"),
        EstadoCita(centro_id=1, codigo="confirmada", nombre="Confirmada"),
        EstadoCita(centro_id=1, codigo="anulada", nombre="Anulada"),
        Gabinete(centro_id=1, nombre="G1"),
        TipoCita(centro_id=1, nombre="Revisión"))
    hoy = date.today()
    session.add_all([
        Cita(centro_id=1, paciente_id=pac.id, fecha=hoy + timedelta(days=7), hora="10:00",
             estado_id=conf.id, gabinete_id=gab.id, tipo_cita_id=tipo.id, colaborador_id=col.id),
        Cita(centro_id=1, paciente_id=pac.id, fecha=hoy, hora="09:00", estado_id=conf.id),
        Cita(centro_id=1, paciente_id=pac.id, fecha=hoy - timedelta(days=30), hora="12:00"),
        Cita(centro_id=1, paciente_id=pac.id, fecha=hoy + timedelta(days=1), hora="11:00",
             estado_id=anul.id),  # anulada: no se enseña
        Cita(centro_id=1, paciente_id=otro_pac.id, fecha=hoy, hora="08:00"),  # de otro paciente
    ])
    session.commit()

    r = InicioPacienteService(session, 1, TODO).resumen(pac.id)["citas"]

    assert r["permitido"] is True
    assert [c["hora"] for c in r["proximas"]] == ["09:00", "10:00"]  # hoy cuenta como próxima
    semana = r["proximas"][1]
    assert semana["doctor"] == "Ana Doc"
    assert semana["gabinete"] == "G1" and semana["tipo"] == "Revisión"
    assert semana["estadoCodigo"] == "confirmada"
    assert [c["fecha"] for c in r["pasadas"]] == [(hoy - timedelta(days=30)).isoformat()]
    assert r["totalPasadas"] == 1


def test_sin_permiso_cada_seccion_se_cierra(session: Session):
    pac, = _add(session, Paciente(centro_id=1, nombre="Juan"))
    r = InicioPacienteService(session, 1, set()).resumen(pac.id)
    assert r["citas"] == {"permitido": False}
    assert r["automatizaciones"] == {"permitido": False}
    assert r["flujo"] == {"permitido": False}


def test_automatizaciones_enviadas_solo_del_paciente(session: Session):
    pac, otro = _add(session, Paciente(centro_id=1, nombre="Juan"), Paciente(centro_id=1, nombre="Otro"))
    session.add_all([
        EnvioAutomatico(centro_id=1, disparador="recordatorio_24h", clave_objetivo="cita:1",
                        fecha_envio=date(2026, 9, 1), paciente_id=pac.id),
        EnvioAutomatico(centro_id=1, disparador="post_visita", clave_objetivo="cita:2",
                        fecha_envio=date(2026, 9, 2), paciente_id=pac.id),
        EnvioAutomatico(centro_id=1, disparador="bienvenida", clave_objetivo="pac:9",
                        fecha_envio=date(2026, 9, 3), paciente_id=otro.id),
    ])
    session.commit()

    a = InicioPacienteService(session, 1, TODO).resumen(pac.id)["automatizaciones"]

    assert a["permitido"] is True
    assert [e["disparador"] for e in a["enviados"]] == ["post_visita", "recordatorio_24h"]
    assert a["enviados"][1]["nombre"] == "Recordatorio 24h antes de cita"
    assert isinstance(a["pendientes"], list)


def test_flujo_en_curso_y_cortarlo(session: Session):
    pac, = _add(session, Paciente(centro_id=1, nombre="Juan", telefono_movil="600111222"))
    conv, = _add(session, Conversacion(centro_id=1, paciente_id=pac.id, telefono="34600111222",
                                       estado_flujo={"intent": "reservar", "paso": "tratamiento"}))

    f = InicioPacienteService(session, 1, TODO).resumen(pac.id)["flujo"]
    assert f["conversacion"]["id"] == conv.id
    assert f["conversacion"]["flujo"] == {"id": "reservar", "nombre": "Reservar cita", "paso": "tratamiento"}
    assert f["conversacion"]["iaPausada"] is False

    assert ComunicacionService(session).cortar_flujo(1, conv.id) is True
    f = InicioPacienteService(session, 1, TODO).resumen(pac.id)["flujo"]
    assert f["conversacion"]["flujo"] is None


def test_no_se_toca_una_conversacion_de_otro_centro(session: Session):
    otro = _otro_centro(session)
    conv, = _add(session, Conversacion(centro_id=otro, telefono="34600999999",
                                       estado_flujo={"intent": "consultar", "paso": "verificar"}))
    svc = ComunicacionService(session)
    assert svc.cortar_flujo(1, conv.id) is False
    assert svc.pausar_ia_conversacion(1, conv.id, 30) is False
    assert svc.reanudar_ia_conversacion(1, conv.id) is False
    session.refresh(conv)
    assert conv.estado_flujo == {"intent": "consultar", "paso": "verificar"}


def test_endpoint_paciente_404_y_ok(client: TestClient, token: str, session: Session):
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/inicio/paciente/999999", headers=h).status_code == 404
    pac, = _add(session, Paciente(centro_id=1, nombre="Juan"))
    r = client.get(f"/inicio/paciente/{pac.id}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["pacienteId"] == pac.id
    assert set(r.json()) == {"pacienteId", "citas", "automatizaciones", "flujo"}


def test_endpoint_cortar_flujo_404_conversacion_ajena(client: TestClient, token: str, session: Session):
    otro = _otro_centro(session)
    conv, = _add(session, Conversacion(centro_id=otro, telefono="34600888888"))
    h = {"Authorization": f"Bearer {token}"}
    assert client.post(f"/comunicacion/conversaciones/{conv.id}/flujo/cortar", headers=h).status_code == 404


def test_conversacion_por_ficha_o_por_telefono_sin_ficha(session: Session):
    pac, = _add(session, Paciente(centro_id=1, nombre="Juan", telefono_movil="600111333", acepta_bots=True))
    otro = _otro_centro(session)
    con_ficha, sin_ficha, ajena = _add(
        session,
        Conversacion(centro_id=1, paciente_id=pac.id, telefono="34600111333"),
        Conversacion(centro_id=1, telefono="34622340363"),            # cita dada sin ficha
        Conversacion(centro_id=otro, telefono="34622340363"))        # mismo móvil, OTRO centro
    svc = InicioPacienteService(session, 1, TODO)

    r = svc.conversacion(pac.id, None)
    assert r["conversacion"]["id"] == con_ficha.id and r["aceptaBots"] is True
    r = svc.conversacion(None, "622340363")
    assert r["conversacion"]["id"] == sin_ficha.id and r["aceptaBots"] is None
    assert r["telefono"] == "34622340363"
    assert svc.conversacion(None, None)["conversacion"] is None
    assert InicioPacienteService(session, 1, set()).conversacion(pac.id, None) == {"permitido": False}
    assert ajena.id != svc.conversacion(None, "622340363")["conversacion"]["id"]


def test_endpoint_conversacion_sin_ficha(client: TestClient, token: str, session: Session):
    conv, = _add(session, Conversacion(centro_id=1, telefono="34655000111"))
    r = client.get("/inicio/conversacion?telefono=655000111", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["conversacion"]["id"] == conv.id


def test_camino_1_si_quedan_tratamientos_previstos(client: TestClient, token: str, session: Session):
    """Regresión: con cita, el endpoint daba 500 (SQL crudo) y el Camino 1 no se abría nunca."""
    from sqlalchemy import text
    session.connection().execute(text(
        "CREATE TABLE IF NOT EXISTS tratamientos_previstos (id INTEGER PRIMARY KEY, centro_id INTEGER, paciente_id INTEGER)"))
    pac, = _add(session, Paciente(centro_id=1, nombre="Juan"))
    cita, = _add(session, Cita(centro_id=1, paciente_id=pac.id, fecha=date.today(), hora="10:00"))
    h = {"Authorization": f"Bearer {token}"}
    r = client.get(f"/pacientes/{pac.id}/consulta/camino?cita_id={cita.id}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["tiene_previstos"] is False
    session.connection().execute(text(
        "INSERT INTO tratamientos_previstos (centro_id, paciente_id, created_at, updated_at) "
        "VALUES (1, :p, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"), {"p": pac.id})
    session.commit()
    r = client.get(f"/pacientes/{pac.id}/consulta/camino?cita_id={cita.id}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["camino"] == 1 and r.json()["tiene_previstos"] is True
