"""Agenda — recursos, gabinetes y horarios. FK a nodos-dios.

La cita vive en core.py. Aquí va lo que la rodea: los recursos
físicos (gabinetes/sillones), los horarios de trabajo y los bloqueos de agenda.

    centro ──< gabinete           (recurso físico: sillón/box)
    centro ──< colaborador_horario >── colaborador   (cuándo trabaja cada doctor)
    cita ──> gabinete (opcional)   (en qué sillón se atiende)
    centro ──< bloqueo_agenda      (vacaciones, festivos, mantenimiento)
"""
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin


class Agenda(TimestampMixin, table=True):
    """Calendario por especialidad/servicio del centro (Odontología, Fisioterapia…)."""
    __tablename__ = "agendas"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    nombre: str = Field(max_length=120, index=True)
    color: Optional[str] = Field(default=None, max_length=9)
    intervalo_min: Optional[int] = Field(default=None)   # granularidad de huecos
    vista_defecto: Optional[str] = Field(default=None, max_length=20)  # Día | Semana
    orden: Optional[int] = Field(default=None)
    activo: bool = Field(default=True, index=True)


class TipoCita(TimestampMixin, table=True):
    """Tipo/motivo de cita que se muestra en la agenda (catálogo; NO el tratamiento clínico)."""
    __tablename__ = "tipos_cita"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    agenda_id: Optional[int] = Field(default=None, foreign_key="agendas.id", index=True)
    nombre: str = Field(max_length=120, index=True)      # Control, Higiene, Urgencia…
    color: Optional[str] = Field(default=None, max_length=9)
    # La duración NO vive aquí: la dicta cada colaborador (ver ColaboradorHorario).
    activo: bool = Field(default=True, index=True)


class EstadoCita(TimestampMixin, table=True):
    """Catálogo de estados de cita (Planificada, Anulada, Finalizada…) con color."""
    __tablename__ = "estados_cita"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    agenda_id: Optional[int] = Field(default=None, foreign_key="agendas.id", index=True)
    codigo: str = Field(max_length=40, index=True)       # planificada | anulada | finalizada…
    nombre: str = Field(max_length=80)
    color: Optional[str] = Field(default=None, max_length=9)
    orden: Optional[int] = Field(default=None)
    activo: bool = Field(default=True, index=True)


class Gabinete(TimestampMixin, table=True):
    """Recurso físico donde se atiende (sillón/box)."""
    __tablename__ = "gabinetes"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    agenda_id: Optional[int] = Field(default=None, foreign_key="agendas.id", index=True)
    nombre: str = Field(max_length=80)          # G1, G2…
    activo: bool = Field(default=True, index=True)


class ColaboradorHorario(TimestampMixin, table=True):
    """Franja de trabajo de un colaborador (día de la semana, con pausa opcional)."""
    __tablename__ = "colaborador_horarios"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    agenda_id: Optional[int] = Field(default=None, foreign_key="agendas.id", index=True)
    colaborador_id: int = Field(foreign_key="colaboradores.id", nullable=False, index=True)
    gabinete_id: Optional[int] = Field(default=None, foreign_key="gabinetes.id", index=True)
    dia_semana: int = Field(index=True)         # 0=lunes … 6=domingo
    hora_inicio: str = Field(max_length=5)      # HH:MM
    hora_fin: str = Field(max_length=5)
    pausa_inicio: Optional[str] = Field(default=None, max_length=5)
    pausa_fin: Optional[str] = Field(default=None, max_length=5)
    activo: bool = Field(default=True, index=True)


class ColaboradorExcepcion(TimestampMixin, table=True):
    """Excepción puntual de horario de un colaborador (rango de fechas, horas a medida)."""
    __tablename__ = "colaborador_excepciones"
    id: Optional[int] = Field(default=None, primary_key=True)
    colaborador_id: int = Field(foreign_key="colaboradores.id", nullable=False, index=True)
    fecha_inicio: date = Field(index=True)
    fecha_fin: date = Field(index=True)
    tipo: Optional[str] = Field(default=None, max_length=40)   # ausencia | horario especial…
    hora_inicio: Optional[str] = Field(default=None, max_length=5)
    hora_fin: Optional[str] = Field(default=None, max_length=5)
    pausa_inicio: Optional[str] = Field(default=None, max_length=5)
    pausa_fin: Optional[str] = Field(default=None, max_length=5)


class BloqueoAgenda(TimestampMixin, table=True):
    """Hueco no disponible: vacaciones, festivo, mantenimiento."""
    __tablename__ = "bloqueos_agenda"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    gabinete_id: Optional[int] = Field(default=None, foreign_key="gabinetes.id", index=True)
    fecha_inicio: datetime = Field(index=True)
    fecha_fin: datetime = Field(index=True)
    motivo: Optional[str] = Field(default=None, max_length=200)
