"""Prótesis / laboratorio — trabajos enviados al laboratorio. FK a nodos-dios.

Un trabajo protésico nace de un acto clínico, se manda a un
laboratorio (proveedor), tiene fases y un coste que entra en gastos.

    cita_tratamiento ──< trabajo_protesico >── proveedor (laboratorio)
    trabajo_protesico ──< trabajo_protesico_fase
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin


class TrabajoProtesico(TimestampMixin, table=True):
    __tablename__ = "trabajos_protesicos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    # acto clínico que lo origina (corona, puente…) y laboratorio que lo fabrica
    cita_tratamiento_id: Optional[int] = Field(
        default=None, foreign_key="cita_tratamiento.id", index=True)
    proveedor_id: Optional[int] = Field(default=None, foreign_key="proveedores.id", index=True)
    descripcion: str = Field(max_length=300)
    estado: str = Field(default="pendiente", index=True)   # pendiente|enviado|recibido|colocado
    fecha_envio: Optional[date] = Field(default=None, index=True)
    fecha_recepcion: Optional[date] = Field(default=None)
    coste: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    fases: list["TrabajoProtesicoFase"] = Relationship(back_populates="trabajo")


class TrabajoProtesicoFase(TimestampMixin, table=True):
    """Fase/prueba de un trabajo (prueba de metal, bizcocho, colocación…)."""
    __tablename__ = "trabajo_protesico_fases"
    id: Optional[int] = Field(default=None, primary_key=True)
    trabajo_id: int = Field(foreign_key="trabajos_protesicos.id", nullable=False, index=True)
    cita_id: Optional[int] = Field(default=None, foreign_key="citas.id", index=True)
    nombre: str = Field(max_length=120)
    completada: bool = Field(default=False, index=True)
    fecha: Optional[date] = Field(default=None)
    trabajo: TrabajoProtesico = Relationship(back_populates="fases")
