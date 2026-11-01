"""IA — artefactos de AURA, la agente de la consulta.

Aura es la responsable de lo que sucede en el gabinete: escucha la sesión, la transcribe
y agiliza los trámites clínicos. Lo que produce cuelga SIEMPRE de una cita (y por ella,
de paciente + centro):

    cita ──< briefing_aura      (preparación previa: con qué llega el paciente)
    cita ──< transcripcion      (la sesión pasada a texto, + SOAP extraído)

El roster completo y sus parcelas están en `domain/config/agentes.py`, que es la fuente
única de verdad. Aquí solo viven las tablas.

Histórico: este módulo definía cinco agentes (Aura/Vista/Escucha/Pluma/Forense) que nunca
llegaron a implementarse — tablas vacías sin una sola referencia en el código, conviviendo
con el roster real. Se retiraron en la migración 029; sobrevive lo que Aura sí usa.

Principio del sistema: la IA propone, el doctor dispone.
"""
from typing import Optional

from sqlmodel import Field

from domain.models._base import TimestampMixin, utcnow


class BriefingAura(TimestampMixin, table=True):
    """Preparación previa generada por AURA antes de la cita."""
    __tablename__ = "briefings_aura"
    id: Optional[int] = Field(default=None, primary_key=True)
    cita_id: int = Field(foreign_key="citas.id", nullable=False, index=True, unique=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    motivo_visita: Optional[str] = Field(default=None, max_length=500)
    briefing_md: Optional[str] = Field(default=None, max_length=8000)
    alertas_clinicas: Optional[str] = Field(default=None, max_length=4000)


class Transcripcion(TimestampMixin, table=True):
    """Escucha activa (ESCUCHA): transcripción de la conversación de consulta."""
    __tablename__ = "transcripciones"
    id: Optional[int] = Field(default=None, primary_key=True)
    cita_id: int = Field(foreign_key="citas.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    texto: str = Field(max_length=20000)
    # info estructurada extraída para el SOAP (JSON serializado)
    extraido_json: Optional[str] = Field(default=None, max_length=8000)
