"""Base común para todos los modelos del dominio.

Reglas de oro (integridad referencial real, cero huérfanos):
- Todo lo multi-tenant lleva `centro_id` (FK a centros, NOT NULL).
- Toda FK lleva índice.
"""
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin(SQLModel):
    """Auditoría mínima en toda tabla."""
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)


class TenantMixin(SQLModel):
    """Todo lo que pertenece a un centro. FK NOT NULL + índice."""
    centro_id: int = Field(
        foreign_key="centros.id",
        nullable=False,
        index=True,
        description="Centro propietario (multi-tenant).",
    )
