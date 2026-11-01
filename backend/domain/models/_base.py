"""Base común para todos los modelos del dominio.

Interconexión brutal = FKs totales. Toda entidad cuelga, vía clave foránea
EXPLÍCITA, de al menos uno de los 5 nodos-dios del sistema:

    centro · paciente · colaborador · cita · tratamiento

Reglas de oro (integridad referencial real, cero huérfanos):
- Todo lo multi-tenant lleva `centro_id` (FK a centros, NOT NULL).
- Todo lo clínico/económico de un paciente lleva `paciente_id` (FK a pacientes).
- Las FK definen `ondelete` explícito (RESTRICT por defecto; CASCADE solo en hijos puros).
- Toda FK lleva índice (los JOINs son el caso de uso principal).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin(SQLModel):
    """Auditoría mínima en toda tabla."""
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)


class TenantMixin(SQLModel):
    """Todo lo que pertenece a un centro. FK NOT NULL + índice.

    `centro_id` es la columna multi-tenant: ninguna fila vive sin centro.
    """
    centro_id: int = Field(
        foreign_key="centros.id",
        nullable=False,
        index=True,
        description="Centro propietario (multi-tenant). Nodo-dios.",
    )
