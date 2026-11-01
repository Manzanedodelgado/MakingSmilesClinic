"""Registro de auditoría.

Toda acción sensible deja rastro (quién · qué · cuándo · desde dónde).
"""
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from domain.models._base import TimestampMixin


class Auditoria(TimestampMixin, table=True):
    __tablename__ = "auditoria"
    id: Optional[int] = Field(default=None, primary_key=True)

    platform_user_id: Optional[int] = Field(
        default=None, foreign_key="platform_users.id", index=True,
    )
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuarios.id", index=True)
    centro_id: Optional[int] = Field(default=None, foreign_key="centros.id", index=True)

    accion: str = Field(max_length=80, index=True)
    recurso: Optional[str] = Field(default=None, max_length=200)
    detalle: Any = Field(default=None, sa_column=Column(JSON))
    ip: Optional[str] = Field(default=None, max_length=64)
    exito: bool = Field(default=True, index=True)
