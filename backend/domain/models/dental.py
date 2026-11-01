"""Odontograma y periodontograma — estado dental por pieza. FK a nodos-dios.

El mapa de la boca del paciente. Cada anotación va por pieza (notación FDI) y,
cuando procede, se enlaza con el acto clínico que la generó.

    paciente ──< odontograma_entrada >── tratamiento (opcional)
    paciente ──< periodontograma_medida
"""
from datetime import date
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin


class OdontogramaEntrada(TimestampMixin, table=True):
    """Estado/hallazgo de una pieza (caries, corona, implante, ausente…)."""
    __tablename__ = "odontograma_entradas"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    pieza: str = Field(max_length=10, index=True)        # FDI: 11, 16, 26…
    cara: Optional[str] = Field(default=None, max_length=20)   # OMDVLC (oclusal, mesial…)
    estado: str = Field(max_length=60)                   # CARIES, CORONA, IMPLANTE, AUSENTE…
    obs: Optional[str] = Field(default=None, max_length=500)   # descripción/tratamiento libre
    tipo_registro: str = Field(default="INICIAL", max_length=20)  # INICIAL | REALIZADO | PRESUPUESTADO
    # acto clínico que originó la anotación (trazabilidad)
    tratamiento_id: Optional[int] = Field(default=None, foreign_key="tratamientos.id", index=True)
    cita_id: Optional[int] = Field(default=None, foreign_key="citas.id", index=True)
    fecha: date = Field(index=True)


class PeriodontogramaMedida(TimestampMixin, table=True):
    """Medidas periodontales de una pieza por SITIOS (6): bolsa, recesión, sangrado, placa, movilidad.

    Origen: ExplPerio (borsa1-6, recessio1-6, sangrat, placa, movilitat). Las filas de una
    misma exploración comparten `exploracion_id`.
    """
    __tablename__ = "periodontograma_medidas"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    cita_id: Optional[int] = Field(default=None, foreign_key="citas.id", index=True)
    exploracion_id: Optional[int] = Field(default=None, index=True)   # agrupa las piezas de una exploración
    pieza: str = Field(max_length=10, index=True)
    # profundidad de bolsa por sitio (mm)
    bolsa_1: Optional[int] = Field(default=None)
    bolsa_2: Optional[int] = Field(default=None)
    bolsa_3: Optional[int] = Field(default=None)
    bolsa_4: Optional[int] = Field(default=None)
    bolsa_5: Optional[int] = Field(default=None)
    bolsa_6: Optional[int] = Field(default=None)
    # recesión por sitio (mm)
    recesion_1: Optional[int] = Field(default=None)
    recesion_2: Optional[int] = Field(default=None)
    recesion_3: Optional[int] = Field(default=None)
    recesion_4: Optional[int] = Field(default=None)
    recesion_5: Optional[int] = Field(default=None)
    recesion_6: Optional[int] = Field(default=None)
    # sangrado y placa por sitio (bool)
    sangrado_1: bool = Field(default=False)
    sangrado_2: bool = Field(default=False)
    sangrado_3: bool = Field(default=False)
    sangrado_4: bool = Field(default=False)
    placa_1: bool = Field(default=False)
    placa_2: bool = Field(default=False)
    placa_3: bool = Field(default=False)
    placa_4: bool = Field(default=False)
    movilidad: Optional[int] = Field(default=None)   # 0-3
    fecha: Optional[date] = Field(default=None, index=True)
