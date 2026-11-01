"""Configuración jerárquica (la única fuente de la verdad).

Jerarquía de resolución (lo más específico gana): plataforma → centro → sistema → usuario.
Una sola tabla `configuraciones`; `null` en un ámbito = "aplica a todo ese nivel".
"""
from typing import Any, Optional

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from domain.models._base import TimestampMixin


class ConfiguracionBase(SQLModel):
    centro_id: Optional[int] = Field(
        default=None, foreign_key="centros.id", index=True,
    )
    sistema: Optional[str] = Field(default=None, max_length=50, index=True)
    usuario_id: Optional[int] = Field(
        default=None, foreign_key="usuarios.id", index=True,
    )
    clave: str = Field(max_length=120, index=True)


class Configuracion(ConfiguracionBase, TimestampMixin, table=True):
    __tablename__ = "configuraciones"
    __table_args__ = (
        UniqueConstraint("centro_id", "sistema", "usuario_id", "clave", name="uq_config_ambito_clave"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    valor: Any = Field(default=None, sa_column=Column(JSON))


class Integracion(TimestampMixin, table=True):
    """Conector externo del centro (WhatsApp/Evolution, email, pasarela…) con su config JSON."""
    __tablename__ = "integraciones"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    tipo: str = Field(max_length=60, index=True)
    nombre: Optional[str] = Field(default=None, max_length=120)
    config: Any = Field(default=None, sa_column=Column(JSON))
    activo: bool = Field(default=True, index=True)
    agente: Optional[str] = Field(default=None, max_length=40)


class ConfiguracionCreate(ConfiguracionBase):
    valor: Any = None


class ConfiguracionRead(ConfiguracionBase):
    id: int
    valor: Any = None
