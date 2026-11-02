"""guardar_soap — regla nueva de urgencia automática (jmd, 12-oct-2026).

Si el paciente no tiene cita VIVA hoy (las anuladas/canceladas/caídas no cuentan) y se le
atende, al guardar el SOAP se crea sola una cita URGENCIA de 15 min en estado Finalizada.
Cumple las mismas reglas que el resto de la web (cita_reglas): gabinete↔doctor desde
colaborador_horarios, dentro del horario del centro. Fuera de horario (pausa, noche, domingo,
festivo) se coloca en el último tramo ya pasado más próximo, restando los 15 min para que la
cita quepa entera dentro del tramo.
"""
from datetime import date, datetime

import pytest
from sqlmodel import Session, select

import application.services.consulta_service as cs
from application.services.config_service import ConfigService
from domain.models.agenda import ColaboradorHorario, EstadoCita, Gabinete, TipoCita
from domain.models.clinico import Soap
from domain.models.core import Cita, Colaborador, Paciente
from domain.models.identidad import Usuario, UsuarioPeriodo

LUNES = date(2026, 10, 12)          # lunes hábil
DOMINGO = date(2026, 10, 18)        # domingo: cerrado → retrocede hasta el viernes 16
_VIERNES_ANTES = date(2026, 10, 16)


def _fijar_reloj(monkeypatch, dt: datetime) -> None:
    """Congela datetime.now()/date.today() de consulta_service en un instante dado."""
    class _DT:
        @classmethod
        def now(cls, tz=None):
            return dt

    class _D(date):
        @classmethod
        def today(cls):
            return dt.date()

    monkeypatch.setattr(cs, "datetime", _DT)
    monkeypatch.setattr(cs, "date", _D)


@pytest.fixture
def clinica(session: Session):
    """Centro 1 con horario lun-vie 10-14/16-20, un gabinete con un doctor REAL activo en esas
    franjas (el evento infranqueable exige doctor existente) y un paciente sin cita."""
    cfg = ConfigService(session)
    cfg.set("centro.horario",
            {"dias": [{"abierto": True, "t1a": "10:00", "t1b": "14:00", "t2a": "16:00", "t2b": "20:00"}] * 5
                     + [{"abierto": False}] * 2},
            centro_id=1)
    session.commit()
    u = Usuario(nombre="Urgencias", apellidos="Doc", email="doc.urgencias@test.local")
    session.add(u); session.commit(); session.refresh(u)
    per = UsuarioPeriodo(usuario_id=u.id, centro_id=1, fecha_alta=date(2020, 1, 1),
                         staff_tipo="DOCTOR")
    session.add(per); session.commit(); session.refresh(per)
    doc = Colaborador(periodo_id=per.id, activo=True)
    session.add(doc); session.commit(); session.refresh(doc)
    gab = Gabinete(centro_id=1, nombre="Box urgencias")
    session.add(gab); session.commit(); session.refresh(gab)
    for ds in range(5):
        for ini, fin in (("10:00", "14:00"), ("16:00", "20:00")):
            session.add(ColaboradorHorario(centro_id=1, colaborador_id=doc.id, gabinete_id=gab.id,
                                           dia_semana=ds, hora_inicio=ini, hora_fin=fin))
    pac = Paciente(centro_id=1, nombre="Urgente", apellidos="Sin Cita", telefono_movil="600000001")
    session.add(pac)
    session.commit(); session.refresh(pac)
    return gab, pac, doc


def _tipo(session: Session, nombre: str) -> TipoCita:
    t = session.exec(select(TipoCita).where(TipoCita.centro_id == 1, TipoCita.nombre == nombre)).first()
    assert t, f"El seed no crea el tipo de cita «{nombre}»"
    return t


def _estado(session: Session, codigo: str) -> EstadoCita:
    e = session.exec(select(EstadoCita).where(EstadoCita.centro_id == 1, EstadoCita.codigo == codigo)).first()
    assert e, f"El seed no crea el estado de cita «{codigo}»"
    return e


def _cita(session: Session, pac: Paciente, hora: str, estado: EstadoCita) -> Cita:
    """Cita válida hoy (el evento infranqueable before_insert la completa desde la ficha)."""
    cita = Cita(centro_id=1, fecha=LUNES, hora=hora, duracion_min=30, paciente_id=pac.id,
                tipo_cita_id=_tipo(session, "Urgencia").id, estado_id=estado.id,
                gabinete_id=_gab_id(session), confirmada=True)
    session.add(cita); session.commit(); session.refresh(cita)
    return cita


def _gab_id(session: Session) -> int:
    return session.exec(select(Gabinete).where(Gabinete.centro_id == 1)).first().id


# ───────────────────────────── dentro de horario ─────────────────────────────

def test_sin_cita_crea_urgencia_finalizada_de_15(session: Session, clinica, monkeypatch):
    _gab, pac, doc = clinica
    _fijar_reloj(monkeypatch, datetime(2026, 10, 12, 11, 30))   # lunes 11:30, en pleno tramo

    res = cs.guardar_soap(session, 1, pac.id, {"subjetivo": "Dolor", "objetivo": "—",
                                               "analisis": "—", "plan": "—"})
    assert res["ok"] is True
    cita = session.get(Cita, res["cita_id"])
    assert cita.fecha == LUNES and cita.hora == "11:30"          # dentro de tramo: «ahora»
    assert cita.duracion_min == 15
    assert cita.tipo_cita_id == _tipo(session, "Urgencia").id
    assert cita.estado_id == _estado(session, "finalizada").id
    assert cita.gabinete_id == _gab_id(session) and cita.colaborador_id == doc.id
    soap = session.exec(select(Soap).where(Soap.cita_id == cita.id)).first()
    assert soap and soap.subjetivo == "Dolor"


def test_con_cita_viva_hoy_no_crea_otra(session: Session, clinica, monkeypatch):
    _gab, pac, doc = clinica
    viva = _cita(session, pac, "11:00", _estado(session, "planificada"))
    _fijar_reloj(monkeypatch, datetime(2026, 10, 12, 11, 30))

    res = cs.guardar_soap(session, 1, pac.id, {"subjetivo": "Dolor"})
    assert res["cita_id"] == viva.id                            # se cuelga de la cita existente
    assert len(session.exec(select(Cita).where(Cita.paciente_id == pac.id)).all()) == 1


def test_cita_anulada_hoy_no_cuenta__crea_la_urgencia(session: Session, clinica, monkeypatch):
    _gab, pac, doc = clinica
    anulada = _cita(session, pac, "11:00", _estado(session, "anulada"))
    _fijar_reloj(monkeypatch, datetime(2026, 10, 12, 11, 35))

    res = cs.guardar_soap(session, 1, pac.id, {"subjetivo": "Dolor"})
    assert res["cita_id"] != anulada.id                          # la anulada no sirve
    nueva = session.get(Cita, res["cita_id"])
    assert nueva.estado_id == _estado(session, "finalizada").id
    assert nueva.tipo_cita_id == _tipo(session, "Urgencia").id and nueva.duracion_min == 15


# ───────────────────────────── fuera de horario ─────────────────────────────

def test_en_pausa__la_urgencia_va_al_final_del_ultimo_tramo(session: Session, clinica, monkeypatch):
    _gab, pac, doc = clinica
    _fijar_reloj(monkeypatch, datetime(2026, 10, 12, 15, 30))   # pausa 14:00-16:00

    res = cs.guardar_soap(session, 1, pac.id, {"subjetivo": "Dolor"})
    cita = session.get(Cita, res["cita_id"])
    assert cita.fecha == LUNES and cita.hora == "13:45"         # fin del tramo de mañana − 15 min
    assert cita.duracion_min == 15 and cita.estado_id == _estado(session, "finalizada").id


def test_de_noche__al_final_del_ultimo_tramo_de_hoy(session: Session, clinica, monkeypatch):
    _gab, pac, doc = clinica
    _fijar_reloj(monkeypatch, datetime(2026, 10, 12, 21, 30))   # after hours

    res = cs.guardar_soap(session, 1, pac.id, {"subjetivo": "Dolor"})
    cita = session.get(Cita, res["cita_id"])
    assert cita.fecha == LUNES and cita.hora == "19:45"         # fin del tramo de tarde − 15 min


def test_un_domingo__retrocede_hasta_el_ultimo_tramo_pasado(session: Session, clinica, monkeypatch):
    _gab, pac, doc = clinica
    _fijar_reloj(monkeypatch, datetime(2026, 10, 18, 11, 0))    # domingo: cerrado

    res = cs.guardar_soap(session, 1, pac.id, {"subjetivo": "Dolor"})
    cita = session.get(Cita, res["cita_id"])
    assert cita.fecha == _VIERNES_ANTES and cita.hora == "19:45"  # viernes: último tramo pasado
    assert cita.duracion_min == 15 and cita.estado_id == _estado(session, "finalizada").id
