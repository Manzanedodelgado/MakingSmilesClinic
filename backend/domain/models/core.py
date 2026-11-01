"""Nodos-dios: centro y colaborador (subconjunto para M01/M02).

El esquema completo (paciente, cita, tratamiento, razón social, geografía…) se porta
módulo a módulo con la paridad de datos (PARIDAD-DATOS.md). Aquí, lo mínimo que
necesitan Identidad y Configuración, con el mismo nombre de tablas y FK.
"""
from datetime import date
from typing import Optional

from sqlmodel import Field, SQLModel

from domain.models._base import TimestampMixin


class CentroBase(SQLModel):
    nombre: str = Field(index=True, min_length=1, max_length=200)
    codigo: Optional[str] = Field(default=None, max_length=20, index=True)
    direccion: Optional[str] = Field(default=None, max_length=300)
    cp: Optional[str] = Field(default=None, max_length=10)
    poblacion: Optional[str] = Field(default=None, max_length=120)
    provincia: Optional[str] = Field(default=None, max_length=120)
    telefono: Optional[str] = Field(default=None, max_length=50)
    telefono_movil: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    web: Optional[str] = Field(default=None, max_length=255)
    instagram: Optional[str] = Field(default=None, max_length=120)
    icono_url: Optional[str] = Field(default=None, max_length=500)
    logo_url: Optional[str] = Field(default=None, max_length=500)
    num_gabinetes: Optional[int] = Field(default=None)
    fecha_alta: Optional[date] = Field(default=None)
    fecha_baja: Optional[date] = Field(default=None)
    activo: bool = Field(default=True, index=True)


class Centro(CentroBase, TimestampMixin, table=True):
    __tablename__ = "centros"
    id: Optional[int] = Field(default=None, primary_key=True)


class Colaborador(TimestampMixin, table=True):
    """El económico de una etapa laboral, 1:1 con un `usuario_periodos`."""
    __tablename__ = "colaboradores"
    id: Optional[int] = Field(default=None, primary_key=True)
    periodo_id: Optional[int] = Field(
        default=None, foreign_key="usuario_periodos.id", index=True, unique=True,
    )
    activo: bool = Field(default=True, index=True)
