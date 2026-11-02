"""INICIO · citas del día (Cover Flow): cada campo sale de SU columna y los filtros acotan.

Regresión: el mapeo por posición estaba desplazado (gabinete recibía tipo_cita_id y tipo
recibía el nombre del gabinete), y la tarjeta enseñaba el id interno en vez del NumPac.
"""
from datetime import date, timedelta

from sqlmodel import Session

from application.services.pulso_service import PulsoService
from domain.models.agenda import Agenda, EstadoCita, Gabinete, TipoCita
from domain.models.core import Cita, Colaborador, Paciente
from domain.models.identidad import Usuario, UsuarioPeriodo


def _add(session: Session, *objs):
    for o in objs:
        session.add(o)
    session.commit()
    for o in objs:
        session.refresh(o)
    return objs


def _doctor(session: Session, nombre: str, baja: date | None = None) -> Colaborador:
    u, = _add(session, Usuario(email=f"{nombre.lower()}@t.es", nombre=nombre, apellidos="Doc",
                               password_hash="x"))
    per, = _add(session, UsuarioPeriodo(usuario_id=u.id, centro_id=1, fecha_alta=date(2020, 1, 1), fecha_baja=baja))
    col, = _add(session, Colaborador(periodo_id=per.id, activo=True))
    return col


def test_citas_hoy_mapea_gabinete_tipo_y_numhistoria(session: Session):
    gab, tipo, est, pac = _add(
        session,
        Gabinete(centro_id=1, nombre="G2"),
        TipoCita(centro_id=1, nombre="Higiene"),
        EstadoCita(centro_id=1, codigo="confirmada", nombre="Confirmada"),
        Paciente(centro_id=1, nombre="Juan Antonio", apellidos="Prueba", num_historia="4134"))
    session.add(Cita(centro_id=1, fecha=date.today(), hora="10:30", duracion_min=30,
                     paciente_id=pac.id, nombre="Juan Antonio", apellidos="Prueba",
                     estado_id=est.id, gabinete_id=gab.id, tipo_cita_id=tipo.id))
    # Cita con ficha pero SIN nombre inline (así migró el 88 % de GELITE): el nombre sale de la ficha.
    session.add(Cita(centro_id=1, fecha=date.today(), hora="11:00", paciente_id=pac.id))
    session.commit()

    citas = PulsoService(session, 1, {"citas.ver"})._hoy()["citas"]

    assert len(citas) == 2
    c = citas[0]
    assert c["gabinete"] == "G2"
    assert c["tipo"] == "Higiene"
    assert c["estado"] == "Confirmada"
    assert c["hora"] == "10:30"
    assert c["numHistoria"] == "4134"
    assert c["paciente"] == "Prueba, Juan Antonio"
    assert citas[1]["paciente"] == "Prueba, Juan Antonio"
    assert citas[1]["numHistoria"] == "4134"


def test_citas_movil_de_la_ficha_y_si_no_el_de_la_cita(session: Session):
    """La cita no siempre copia el móvil; sin él, Inicio decía "sin móvil" a pacientes que sí lo tienen."""
    con, sin = _add(session, Paciente(centro_id=1, nombre="Con", telefono_movil="631000111"),
                    Paciente(centro_id=1, nombre="Sin"))
    session.add_all([
        Cita(centro_id=1, fecha=date.today(), hora="09:00", paciente_id=con.id),  # cita sin móvil
        Cita(centro_id=1, fecha=date.today(), hora="09:30", paciente_id=con.id, telefono_movil="699999999"),
        Cita(centro_id=1, fecha=date.today(), hora="10:00", paciente_id=sin.id, telefono_movil="644000222"),
    ])
    session.commit()

    citas = PulsoService(session, 1, {"citas.ver"})._hoy()["citas"]

    assert [c["telefono"] for c in citas] == ["631000111", "631000111", "644000222"]


def test_citas_filtra_por_fecha_doctor_gabinete_agenda_estado_tipo(session: Session):
    ag1, ag2 = _add(session, Agenda(centro_id=1, nombre="A1"), Agenda(centro_id=1, nombre="A2"))
    g1, g2 = _add(session, Gabinete(centro_id=1, agenda_id=ag1.id, nombre="Box 1"),
                  Gabinete(centro_id=1, agenda_id=ag2.id, nombre="Box 2"))
    t1, t2 = _add(session, TipoCita(centro_id=1, nombre="Revisión"), TipoCita(centro_id=1, nombre="Urgencia"))
    planif, anulada = _add(session, EstadoCita(centro_id=1, codigo="planificada", nombre="Planificada"),
                           EstadoCita(centro_id=1, codigo="anulada", nombre="Anulada"))
    d1, d2 = _doctor(session, "Mario"), _doctor(session, "Irene")
    dia = date(2026, 6, 15)
    base = dict(centro_id=1, fecha=dia, nombre="X", apellidos="Y", estado_id=planif.id)
    _add(session,
         Cita(**base, hora="09:00", agenda_id=ag1.id, gabinete_id=g1.id, colaborador_id=d1.id, tipo_cita_id=t1.id),
         Cita(**base, hora="10:00", agenda_id=ag2.id, gabinete_id=g2.id, colaborador_id=d2.id, tipo_cita_id=t2.id),
         Cita(**{**base, "estado_id": anulada.id}, hora="11:00", agenda_id=ag1.id, colaborador_id=d1.id),
         Cita(**{**base, "fecha": dia + timedelta(days=1)}, hora="12:00", agenda_id=ag1.id))
    s = PulsoService(session, 1, {"citas.ver"})

    horas = lambda **f: [c["hora"] for c in s.citas(dia, **f)["citas"]]  # noqa: E731
    assert horas() == ["09:00", "10:00"]            # la anulada no sale; la de otro día tampoco
    assert horas(colaborador_id=d1.id) == ["09:00"]
    assert horas(gabinete_id=g2.id) == ["10:00"]
    assert horas(agenda_id=ag1.id) == ["09:00"]
    assert horas(tipo_cita_id=t2.id) == ["10:00"]
    assert horas(estado_id=planif.id) == ["09:00", "10:00"]
    assert horas(agenda_id=ag1.id, gabinete_id=g2.id) == []
    assert s.citas(dia)["citas"][0]["doctor"] == "Mario Doc"
    assert s.citas(dia)["citas"][0]["estadoCodigo"] == "planificada"
    est = {e["codigo"]: e["id"] for e in s.citas(dia)["opciones"]["estados"]}
    assert est.get("planificada") == planif.id and "anulada" not in est


def test_opciones_doctor_solo_personal_activo_y_gabinetes_por_agenda(session: Session):
    ag1, ag2 = _add(session, Agenda(centro_id=1, nombre="A1"), Agenda(centro_id=1, nombre="A2"))
    _add(session, Gabinete(centro_id=1, agenda_id=ag1.id, nombre="Box 1"),
         Gabinete(centro_id=1, agenda_id=ag2.id, nombre="Box 2"))
    activo = _doctor(session, "Activa")
    # activo=True pero con baja (caso real "Test Admin"): NUNCA en un selector.
    de_baja = _doctor(session, "Baja", baja=date(2026, 9, 26))
    s = PulsoService(session, 1, {"citas.ver"})

    op = s.citas(date.today())["opciones"]
    ids = [d["id"] for d in op["doctores"]]
    assert activo.id in ids and de_baja.id not in ids
    assert {a["nombre"] for a in op["agendas"]} >= {"A1", "A2"}
    assert [g["nombre"] for g in s.citas(date.today(), agenda_id=ag1.id)["opciones"]["gabinetes"]] == ["Box 1"]


def test_sin_permiso_no_hay_citas(session: Session):
    _add(session, Cita(centro_id=1, fecha=date.today(), hora="09:00", nombre="X"))
    r = PulsoService(session, 1, set()).citas(date.today())
    assert r["citas"] == [] and r["permitido"] is False


def test_endpoint_inicio_citas(client, token, session: Session):
    from domain.models.agenda import Gabinete as G
    g, = _add(session, G(centro_id=1, nombre="Box E"))
    _add(session, Cita(centro_id=1, fecha=date(2026, 6, 15), hora="09:00", nombre="A", gabinete_id=g.id),
         Cita(centro_id=1, fecha=date(2026, 6, 15), hora="10:00", nombre="B"))
    h = {"Authorization": f"Bearer {token}"}
    r = client.get("/inicio/citas", params={"fecha": "2026-06-15"}, headers=h)
    assert r.status_code == 200, r.text
    assert [c["hora"] for c in r.json()["citas"]] == ["09:00", "10:00"]
    r = client.get("/inicio/citas", params={"fecha": "2026-06-15", "gabinete_id": g.id}, headers=h)
    assert [c["hora"] for c in r.json()["citas"]] == ["09:00"]
    # /auth/login fija cookie httpOnly además del Bearer: el cliente la conserva,
    # así que para probar "sin autenticar" hay que limpiar el jar primero.
    client.cookies.clear()
    assert client.get("/inicio/citas", params={"fecha": "2026-06-15"}).status_code == 401
