"""Tests del motor de huecos (dominio puro)."""
from datetime import date, datetime

from domain.services.disponibilidad import (
    Bloqueo, Horario, Ocupacion, a_hhmm, a_min, calcular_huecos,
)

# lunes 2026-06-29 (weekday 0)
LUNES = date(2026, 6, 29)
HOY = date(2026, 6, 28)   # domingo → "mañana" es lunes


def _horario_lunes(ini="09:00", fin="11:00", pini=None, pfin=None):
    return Horario(colaborador_id=1, gabinete_id=1, dia_semana=0,
                   hora_inicio=ini, hora_fin=fin, pausa_inicio=pini, pausa_fin=pfin)


def test_parse_horas():
    assert a_min("09:30") == 570
    assert a_hhmm(570) == "09:30"


def test_huecos_franja_simple():
    h = calcular_huecos([_horario_lunes()], [], [], hoy=HOY, dias=1, duracion_min=30)
    horas = [x.hora for x in h if x.fecha == LUNES]
    assert horas == ["09:00", "09:30", "10:00", "10:30"]   # 2h / 30min = 4 huecos


def test_pausa_excluye_huecos():
    h = calcular_huecos([_horario_lunes(pini="10:00", pfin="10:30")], [], [],
                        hoy=HOY, dias=1, duracion_min=30)
    horas = [x.hora for x in h]
    assert "10:00" not in horas        # pausa
    assert horas == ["09:00", "09:30", "10:30"]


def test_cita_ocupa_hueco():
    ocup = [Ocupacion(colaborador_id=1, fecha=LUNES, hora="09:30", duracion_min=30)]
    h = calcular_huecos([_horario_lunes()], ocup, [], hoy=HOY, dias=1, duracion_min=30)
    horas = [x.hora for x in h]
    assert "09:30" not in horas
    assert horas == ["09:00", "10:00", "10:30"]


def test_bloqueo_excluye_dia():
    b = [Bloqueo(fecha_inicio=datetime(2026, 6, 29, 0, 0), fecha_fin=datetime(2026, 6, 29, 23, 59))]
    h = calcular_huecos([_horario_lunes()], [], b, hoy=HOY, dias=1, duracion_min=30)
    assert h == []


def test_no_ofrece_hoy():
    # horario sólo lunes; si hoy ES lunes, "mañana" es martes → sin huecos ese día
    h = calcular_huecos([_horario_lunes()], [], [], hoy=LUNES, dias=1, duracion_min=30)
    assert all(x.fecha != LUNES for x in h)
