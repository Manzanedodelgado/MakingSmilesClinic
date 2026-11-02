"""id_cita y sellos de la cita — regla de identidad (jmd, 12-oct-2026).

`id_cita` nace con la cita y NO cambia al modificarla (mover, reprogramar, cambiar estado).
Copiar una cita de estado final (finalizada, cancelada, anulada) —lo que hace el personal para
la nueva cita que pide el paciente— es una cita NUEVA: recibe id_cita nuevo. La cita lleva
además fecha_hora_creacion (inmutable, se fija al crear) y fecha_hora_modificacion (se
renueva en cada modificación). Todo lo garantizan los eventos de cita_reglas.
"""
from datetime import date, datetime

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from application.services.config_service import ConfigService
from domain.models.agenda import ColaboradorHorario, EstadoCita, Gabinete, TipoCita
from domain.models.core import Cita, Colaborador, Paciente
from domain.models.identidad import Usuario, UsuarioPeriodo

LUNES = date(2026, 10, 12)


@pytest.fixture
def clinica(session: Session):
    """Mismo escenario que test_soap_urgencia: horario lun-vie 10-14/16-20, un gabinete con
    un doctor REAL activo en esas franjas (el evento infranqueable exige gabinete↔doctor) y
    un paciente."""
    cfg = ConfigService(session)
    cfg.set("centro.horario",
            {"dias": [{"abierto": True, "t1a": "10:00", "t1b": "14:00", "t2a": "16:00", "t2b": "20:00"}] * 5
                     + [{"abierto": False}] * 2},
            centro_id=1)
    session.commit()
    u = Usuario(nombre="Identidad", apellidos="Doc", email="doc.identidad@test.local")
    session.add(u); session.commit(); session.refresh(u)
    per = UsuarioPeriodo(usuario_id=u.id, centro_id=1, fecha_alta=date(2020, 1, 1),
                         staff_tipo="DOCTOR")
    session.add(per); session.commit(); session.refresh(per)
    doc = Colaborador(periodo_id=per.id, activo=True)
    session.add(doc); session.commit(); session.refresh(doc)
    gab = Gabinete(centro_id=1, nombre="Box identidad")
    session.add(gab); session.commit(); session.refresh(gab)
    for ds in range(5):
        for ini, fin in (("10:00", "14:00"), ("16:00", "20:00")):
            session.add(ColaboradorHorario(centro_id=1, colaborador_id=doc.id, gabinete_id=gab.id,
                                           dia_semana=ds, hora_inicio=ini, hora_fin=fin))
    pac = Paciente(centro_id=1, nombre="Id", apellidos="Entidad", telefono_movil="600000002")
    session.add(pac)
    session.commit(); session.refresh(pac)
    return gab, pac, doc


def _estado(session: Session, codigo: str) -> EstadoCita:
    e = session.exec(select(EstadoCita).where(EstadoCita.centro_id == 1, EstadoCita.codigo == codigo)).first()
    assert e, f"El seed no crea el estado de cita «{codigo}»"
    return e


def _cita(session: Session, pac: Paciente, hora: str, estado: EstadoCita,
          id_cita: int | None = None) -> Cita:
    """Cita válida (el evento before_insert la completa). `id_cita` simula una copia."""
    tipo = session.exec(select(TipoCita).where(TipoCita.centro_id == 1,
                                               TipoCita.nombre == "Urgencia")).first()
    gab = session.exec(select(Gabinete).where(Gabinete.centro_id == 1)).first()
    cita = Cita(centro_id=1, fecha=LUNES, hora=hora, duracion_min=30, paciente_id=pac.id,
                tipo_cita_id=tipo.id, estado_id=estado.id, gabinete_id=gab.id, id_cita=id_cita)
    session.add(cita); session.commit(); session.refresh(cita)
    return cita


def _naive(dt: datetime) -> datetime:
    """SQLite devuelve lo guardado sin tz y utcnow() trae tz; para comparar por igual."""
    return dt.replace(tzinfo=None)


# ───────────────────────────── nacimiento ─────────────────────────────

def test_cita_nueva__id_cita_y_sellos_nacen_juntos(session: Session, clinica):
    _gab, pac, _doc = clinica
    c = _cita(session, pac, "10:00", _estado(session, "planificada"))
    assert c.id_cita is not None
    assert c.fecha_hora_creacion is not None and c.fecha_hora_modificacion is not None
    assert c.fecha_hora_creacion == c.fecha_hora_modificacion   # recién nacida: aún sin cambios


def test_dos_citas__cada_una_con_su_id_cita(session: Session, clinica):
    _gab, pac, _doc = clinica
    a = _cita(session, pac, "10:00", _estado(session, "planificada"))
    b = _cita(session, pac, "11:00", _estado(session, "planificada"))
    assert a.id_cita != b.id_cita


# ───────────────────────────── modificación ─────────────────────────────

def test_modificar__id_cita_y_creacion_inmutables__modificacion_se_renueva(session: Session, clinica):
    _gab, pac, _doc = clinica
    c = _cita(session, pac, "10:00", _estado(session, "planificada"))
    id0, creacion0 = c.id_cita, c.fecha_hora_creacion

    # Congelamos el sello de modificación a mano (SQL directo: los eventos no se disparan).
    session.connection().execute(
        text("UPDATE citas SET fecha_hora_modificacion = '2000-01-01 00:00:00' WHERE id = :i"),
        {"i": c.id})
    session.commit(); session.refresh(c)
    assert _naive(c.fecha_hora_modificacion) == datetime(2000, 1, 1)

    c.notas = "tocada"                            # cualquier modificación…
    c.id_cita = id0 + 1_000_000                   # …intentando reescribir la identidad…
    c.fecha_hora_creacion = datetime(1999, 1, 1)  # …y el sello de creación
    session.add(c); session.commit(); session.refresh(c)

    assert c.id_cita == id0                                   # el hilo no cambia nunca
    assert c.fecha_hora_creacion == creacion0                 # el alta tampoco
    assert _naive(c.fecha_hora_modificacion) > datetime(2000, 1, 1)   # …pero el de modificación sí


# ───────────────────────── copia de una cita final ─────────────────────────

@pytest.mark.parametrize("codigo", ["finalizada", "cancelada", "anulada"])
def test_copia_de_cita_final__id_cita_nuevo(session: Session, clinica, codigo):
    """Regla de jmd: el personal copia la cita finalizada/cancelada/anulada y la pega en el
    nuevo hueco → es una cita NUEVA, con id_cita nuevo (la original conserva el suyo)."""
    _gab, pac, _doc = clinica
    original = _cita(session, pac, "10:00", _estado(session, codigo))
    copia = _cita(session, pac, "12:00", _estado(session, "planificada"), id_cita=original.id_cita)
    assert copia.id_cita != original.id_cita
    assert copia.id_cita > original.id_cita             # asignado nuevo, no reutilizado
    session.refresh(original)
    assert original.id_cita != copia.id_cita
