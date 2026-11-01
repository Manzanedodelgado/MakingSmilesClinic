"""🧠 CEREBRO — Configuración jerárquica (la única fuente de la verdad).

Principio (PRINCIPIOS-ARQUITECTURA §1): CONFIG es la fuente de la verdad. El
resto del organismo NO inventa nada: cada sistema lee aquí su comportamiento.

Jerarquía de resolución (lo más específico gana):

    plataforma  →  centro  →  sistema  →  usuario

Implementación: una sola tabla `configuraciones` cuyas filas se identifican por
un ámbito (centro_id / sistema / usuario_id, todos opcionales). `null` significa
"aplica a todo ese nivel". El servicio resuelve una clave eligiendo la fila más
específica presente (ver application/services/config_service.py).

    centro_id=NULL, sistema=NULL   → valor global de plataforma
    centro_id=7,    sistema=NULL   → valor para todo el centro 7
    centro_id=7,    sistema=agenda → valor del sistema agenda en el centro 7
    + usuario_id                   → preferencia de un usuario concreto
"""
from typing import Any, Optional

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from domain.models._base import TimestampMixin


class ConfiguracionBase(SQLModel):
    centro_id: Optional[int] = Field(
        default=None, foreign_key="centros.id", index=True,
        description="NULL = global de plataforma; si no, config de ese centro.",
    )
    sistema: Optional[str] = Field(
        default=None, max_length=50, index=True,
        description="NULL = aplica a todos los sistemas; si no: cuidarte|escucharte|gestionalo|ia|centinela…",
    )
    usuario_id: Optional[int] = Field(
        default=None, foreign_key="usuarios.id", index=True,
        description="NULL = no es preferencia de usuario; si no, override personal.",
    )
    clave: str = Field(max_length=120, index=True, description="p.ej. agenda.intervalo_min")


class Configuracion(ConfiguracionBase, TimestampMixin, table=True):
    """Una entrada de configuración en un ámbito concreto."""
    __tablename__ = "configuraciones"
    __table_args__ = (
        UniqueConstraint(
            "centro_id", "sistema", "usuario_id", "clave",
            name="uq_config_ambito_clave",
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    # Valor JSON: admite escalar, lista u objeto. Imágenes = URL/fichero, nunca base64.
    valor: Any = Field(default=None, sa_column=Column(JSON))


class Integracion(TimestampMixin, table=True):
    """Conector externo del centro (WhatsApp/Evolution, email, pasarela…) con su config JSON."""
    __tablename__ = "integraciones"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    tipo: str = Field(max_length=60, index=True)         # whatsapp | email | pasarela_pago | …
    nombre: Optional[str] = Field(default=None, max_length=120)
    config: Any = Field(default=None, sa_column=Column(JSON))   # credenciales/parámetros
    activo: bool = Field(default=True, index=True)
    # Solo relevante para tipo='llm': qué agente/tarea usa este modelo (alex | consulta_viva |
    # gestoria_gastos | gestoria_facturas). NULL = modelo compartido (retrocompatible).
    agente: Optional[str] = Field(default=None, max_length=40)


class ConfiguracionCreate(ConfiguracionBase):
    valor: Any = None


class ConfiguracionRead(ConfiguracionBase):
    id: int
    valor: Any = None
