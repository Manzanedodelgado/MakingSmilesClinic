"""Motor de huecos de agenda (dominio puro). Sin BBDD: recibe horarios, citas y
bloqueos como datos planos y calcula los huecos libres. Así es 100% testeable.

Un hueco es libre si: (1) cae dentro de una franja de trabajo del colaborador ese
día de la semana, (2) no solapa su pausa, (3) no solapa una cita suya, (4) no cae
en un bloqueo de agenda. Los huecos se ofrecen en pasos de `duracion_min`.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional


def a_min(hhmm: str) -> int:
    """'HH:MM' → minutos desde medianoche."""
    h, m = (hhmm or "0:0").split(":")[:2]
    return int(h) * 60 + int(m)


def a_hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _solapa(ini_a: int, fin_a: int, ini_b: int, fin_b: int) -> bool:
    return ini_a < fin_b and ini_b < fin_a


@dataclass
class Horario:
    colaborador_id: int
    gabinete_id: Optional[int]
    dia_semana: int            # 0=lunes … 6=domingo
    hora_inicio: str
    hora_fin: str
    pausa_inicio: Optional[str] = None
    pausa_fin: Optional[str] = None


@dataclass
class Ocupacion:
    colaborador_id: Optional[int]
    fecha: date
    hora: str                  # HH:MM
    duracion_min: int


@dataclass
class Bloqueo:
    fecha_inicio: datetime
    fecha_fin: datetime
    colaborador_id: Optional[int] = None


@dataclass
class Hueco:
    fecha: date
    hora: str
    colaborador_id: int
    gabinete_id: Optional[int]


def _bloqueado(b: Bloqueo, d: date, ini: int, fin: int, colab: int) -> bool:
    if b.colaborador_id is not None and b.colaborador_id != colab:
        return False
    inicio = b.fecha_inicio
    fin_b = b.fecha_fin
    dia_ini = datetime(d.year, d.month, d.day, ini // 60, ini % 60)
    dia_fin = datetime(d.year, d.month, d.day, fin // 60, fin % 60)
    return dia_ini < fin_b and inicio < dia_fin


def calcular_huecos(horarios: list[Horario], ocupaciones: list[Ocupacion],
                    bloqueos: list[Bloqueo], *, hoy: date, dias: int = 7,
                    duracion_min: int = 30, max_huecos: int = 12) -> list[Hueco]:
    """Huecos libres desde mañana hasta hoy+dias (no se ofrece para hoy mismo)."""
    # Índice de ocupación por (colaborador, fecha) → lista de (ini, fin) en minutos
    ocup: dict[tuple, list[tuple[int, int]]] = {}
    for o in ocupaciones:
        ini = a_min(o.hora)
        ocup.setdefault((o.colaborador_id, o.fecha), []).append((ini, ini + (o.duracion_min or duracion_min)))

    huecos: list[Hueco] = []
    for delta in range(1, dias + 1):
        d = hoy + timedelta(days=delta)
        for h in horarios:
            if h.dia_semana != d.weekday():
                continue
            paso = duracion_min
            ini_franja, fin_franja = a_min(h.hora_inicio), a_min(h.hora_fin)
            pausa = (a_min(h.pausa_inicio), a_min(h.pausa_fin)) if h.pausa_inicio and h.pausa_fin else None
            t = ini_franja
            while t + duracion_min <= fin_franja:
                fin = t + duracion_min
                libre = True
                if pausa and _solapa(t, fin, pausa[0], pausa[1]):
                    libre = False
                if libre:
                    for (ci, cf) in ocup.get((h.colaborador_id, d), []):
                        if _solapa(t, fin, ci, cf):
                            libre = False
                            break
                if libre:
                    for b in bloqueos:
                        if _bloqueado(b, d, t, fin, h.colaborador_id):
                            libre = False
                            break
                if libre:
                    huecos.append(Hueco(d, a_hhmm(t), h.colaborador_id, h.gabinete_id))
                    if len(huecos) >= max_huecos:
                        return huecos
                t += paso
    return huecos
