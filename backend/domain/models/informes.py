"""Informes guardados — definiciones de informe del editor (tabla dinámica moderna).

Un informe = nombre + entidad del catálogo + una `definicion` JSON con las columnas
elegidas, los filtros, el orden y el límite. NO guarda datos: es la consulta. Al
ejecutarlo, el motor (informes_router) traduce la definición a SQL seguro (allowlist
del catálogo + parámetros) y devuelve las filas reales.
"""
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field

from domain.models._base import TimestampMixin


class Informe(TimestampMixin, table=True):
    __tablename__ = "informes"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    nombre: str = Field(max_length=160, index=True)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    entidad: str = Field(max_length=40)                              # clave de entidad del catálogo
    definicion: Any = Field(default=None, sa_column=Column(JSON))    # {columnas, filtros, orden, limite}
    creado_por: Optional[int] = Field(default=None)                  # usuario_id
