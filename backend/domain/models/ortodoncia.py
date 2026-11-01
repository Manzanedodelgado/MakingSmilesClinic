"""Ortodoncia — casos de tratamiento largo con revisiones. FK a nodos-dios.

Un caso de orto es un tratamiento
prolongado (meses/años) con revisiones periódicas e intervenciones.

    paciente ──< caso_ortodoncia >── colaborador (+ tratamiento)
    caso_ortodoncia ──< intervencion_ortodoncia >── cita
"""
from datetime import date
from typing import Any, Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin


class CasoOrtodoncia(TimestampMixin, table=True):
    __tablename__ = "casos_ortodoncia"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    tratamiento_id: Optional[int] = Field(default=None, foreign_key="tratamientos.id", index=True)
    aparato: Optional[str] = Field(default=None, max_length=120)   # brackets, alineadores…
    estado: str = Field(default="activo", index=True)
    fecha_inicio: date = Field(index=True)
    fecha_fin_prevista: Optional[date] = Field(default=None)
    mediciones_json: Any = Field(default=None, sa_column=Column(JSON))  # SNA, SNB, ANB, etc (40+ parámetros)
    diagnostico_texto: Optional[str] = Field(default=None)  # Diagnóstico clínico (LLM generado)
    diagnostico_clase: Optional[str] = Field(default=None)  # Clase I/II/III
    diagnostico_patron: Optional[str] = Field(default=None)  # Patrón vertical (hiper/hipodivergente/normohipso)
    plan_tratamiento_json: Any = Field(default=None, sa_column=Column(JSON))  # Fases, duración, aparatología
    intervenciones: list["IntervencionOrtodoncia"] = Relationship(back_populates="caso")


class IntervencionOrtodoncia(TimestampMixin, table=True):
    """Revisión/ajuste del caso (cada visita de control de orto)."""
    __tablename__ = "intervenciones_ortodoncia"
    id: Optional[int] = Field(default=None, primary_key=True)
    caso_id: int = Field(foreign_key="casos_ortodoncia.id", nullable=False, index=True)
    cita_id: Optional[int] = Field(default=None, foreign_key="citas.id", index=True)
    fecha: date = Field(index=True)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    caso: CasoOrtodoncia = Relationship(back_populates="intervenciones")


class EstudioOrtodoncia(TimestampMixin, table=True):
    """Sesión de registros fotográficos del paciente en un momento del tratamiento.

    Es el "estudio" que el doctor toma con la app: una serie de fotos estandarizada
    (protocolo AAO, ver domain/services/protocolo_ortodoncia.py) en una etapa concreta
    (inicial / progreso / final). Puede colgar de un caso de orto, pero no lo exige
    (un estudio inicial se toma ANTES de abrir el caso).
    """
    __tablename__ = "estudios_ortodoncia"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    caso_id: Optional[int] = Field(default=None, foreign_key="casos_ortodoncia.id", index=True)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    etapa: str = Field(default="inicial", index=True)   # inicial | progreso | final
    fecha: date = Field(index=True)
    estado: str = Field(default="en_progreso", index=True)  # en_progreso | completado
    notas: Optional[str] = Field(default=None, max_length=500)
    fotos: list["FotoOrtodoncia"] = Relationship(
        back_populates="estudio",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class FotoOrtodoncia(TimestampMixin, table=True):
    """Una foto de un estudio, ocupando UNA ranura del protocolo (tipo).

    El fichero real vive en disco (nunca en BD, nunca base64) bajo `media/ortodoncia/`
    y se sirve SIEMPRE autenticado y con guard de centro (PII/RGPD), jamás por StaticFiles.
    Una ranura por estudio: re-tomar una foto reemplaza la anterior (unicidad tipo+estudio).
    """
    __tablename__ = "fotos_ortodoncia"
    id: Optional[int] = Field(default=None, primary_key=True)
    estudio_id: int = Field(foreign_key="estudios_ortodoncia.id", nullable=False, index=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    tipo: str = Field(index=True, max_length=40)   # código de ranura del protocolo
    archivo: str = Field(max_length=255)           # ruta relativa a media/ (p.ej. ortodoncia/12/frontal_reposo_ab.jpg)
    ancho: Optional[int] = Field(default=None)
    alto: Optional[int] = Field(default=None)
    estudio: EstudioOrtodoncia = Relationship(back_populates="fotos")
