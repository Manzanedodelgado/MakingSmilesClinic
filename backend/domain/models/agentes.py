"""Agentes IA configurables — modelo de datos del fundamento (Sección 1 de la spec
docs/superpowers/specs/2026-09-23-agentes-ia-configuracion-design.md).

    centro ──< agente ──< agente_capacidad >── capacidad_catalogo

`capacidades_catalogo` es GLOBAL (no depende de centro): es la biblioteca de
capacidades reales ya implementadas en código. `agente_capacidades` es la tabla
puente que dice qué capacidades tiene activas cada agente de cada centro.
"""
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field

from domain.models._base import TimestampMixin


class Agente(TimestampMixin, table=True):
    """Un agente de IA configurable, de base o creado por un centro."""
    __tablename__ = "agentes"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    nombre: str = Field(max_length=80)
    nombre_presentacion: Optional[str] = Field(default=None, max_length=120)
    avatar_url: Optional[str] = Field(default=None, max_length=300)
    audiencia: str = Field(max_length=20, index=True)  # paciente|staff|superuser|facturacion|sistema
    rol_sub: Optional[str] = Field(default=None, max_length=60)
    activo: bool = Field(default=False)
    modo_activacion: str = Field(default="manual", max_length=20)  # manual|programado|ambos
    programacion: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    modelo_llm: Optional[str] = Field(default=None, max_length=80)
    config_key: str = Field(max_length=80)
    es_agente_base: bool = Field(default=False, index=True)


class CapacidadCatalogo(TimestampMixin, table=True):
    """Biblioteca compartida de capacidades reales — cada fila apunta a una
    función Python ya escrita (`ejecutor`), nunca a código libre."""
    __tablename__ = "capacidades_catalogo"
    id: Optional[int] = Field(default=None, primary_key=True)
    clave: str = Field(max_length=60, unique=True, index=True)
    descripcion: str = Field(max_length=300)
    ejecutor: str = Field(max_length=120)
    parametros: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class AgenteCapacidad(TimestampMixin, table=True):
    """Tabla puente: qué capacidades tiene activas cada agente."""
    __tablename__ = "agente_capacidades"
    id: Optional[int] = Field(default=None, primary_key=True)
    agente_id: int = Field(foreign_key="agentes.id", nullable=False, index=True)
    capacidad_id: int = Field(foreign_key="capacidades_catalogo.id", nullable=False, index=True)
    activa: bool = Field(default=True)


class AgentePersonalidad(TimestampMixin, table=True):
    """Personalidad en dos capas (Sección 4 spec): base + aprendida. Prompt final = base + aprendida."""
    __tablename__ = "agente_personalidad"
    id: Optional[int] = Field(default=None, primary_key=True)
    agente_id: int = Field(foreign_key="agentes.id", nullable=False, index=True)
    capa: str = Field(max_length=10, index=True)  # base | aprendida
    idioma: str = Field(default="es", max_length=10)
    tono: Optional[str] = Field(default=None, max_length=500)
    cercania: Optional[int] = Field(default=None)
    proactividad: Optional[int] = Field(default=None)
    formalidad: Optional[int] = Field(default=None)
    bienvenida: Optional[str] = Field(default=None, max_length=500)
    despedida: Optional[str] = Field(default=None, max_length=500)
    acento: Optional[str] = Field(default=None, max_length=40)
    velocidad: Optional[str] = Field(default=None, max_length=20)
    regla_extra: Optional[str] = Field(default=None, max_length=1000)


class AgentePermisoAdmin(TimestampMixin, table=True):
    """Quién puede administrar un agente (Sección 6). Reutiliza roles existentes."""
    __tablename__ = "agente_permisos_admin"
    id: Optional[int] = Field(default=None, primary_key=True)
    agente_id: int = Field(foreign_key="agentes.id", nullable=False, index=True)
    rol_o_usuario: str = Field(max_length=80, index=True)  # nombre de rol o "user:42"
    puede_ver: bool = Field(default=True)
    puede_editar: bool = Field(default=False)


class AgenteCanalAjuste(TimestampMixin, table=True):
    """Ajuste fino por canal (Sección 7), capa sobre personalidad base+aprendida."""
    __tablename__ = "agente_canal_ajuste"
    id: Optional[int] = Field(default=None, primary_key=True)
    agente_id: int = Field(foreign_key="agentes.id", nullable=False, index=True)
    canal: str = Field(max_length=20, index=True)  # whatsapp|voz|chat_interno|superuser
    longitud_max: Optional[int] = Field(default=None)
    usa_emojis: Optional[bool] = Field(default=None)
    ritmo: Optional[str] = Field(default=None, max_length=120)
    extras: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
