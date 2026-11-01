"""🛡️ CENTINELA — registro de auditoría.

Toda acción sensible deja rastro (quién · qué · cuándo · desde dónde). En F0 se
auditan login y cambios de config; los demás órganos registrarán aquí sus
acciones sensibles.
"""
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from domain.models._base import TimestampMixin


class Auditoria(TimestampMixin, table=True):
    __tablename__ = "auditoria"
    id: Optional[int] = Field(default=None, primary_key=True)

    # Autor: puede ser un operador de plataforma o un usuario de centro (uno de los dos).
    platform_user_id: Optional[int] = Field(
        default=None, foreign_key="platform_users.id", index=True,
    )
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuarios.id", index=True)
    centro_id: Optional[int] = Field(default=None, foreign_key="centros.id", index=True)

    accion: str = Field(max_length=80, index=True)   # p.ej. auth.login, config.set
    recurso: Optional[str] = Field(default=None, max_length=200)  # p.ej. config:agenda.intervalo_min
    detalle: Any = Field(default=None, sa_column=Column(JSON))
    ip: Optional[str] = Field(default=None, max_length=64)
    exito: bool = Field(default=True, index=True)
