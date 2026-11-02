"""API INTERNA para los operadores de Jarvis (.91).

Jarvis piensa; la web manda. El operador pide aquí lo que el agente usaría en la web (system,
ejemplos, historial y herramientas) y ejecuta sus herramientas a través de la web, que sigue
aplicando sus reglas (y, con Alex, su verificación de identidad). Protegido por `X-Internal-Key`.

- alex: WhatsApp de pacientes (por teléfono).
- victor, aura, gestor: chat del equipo en la web (el permiso de entrada lo comprueba su router).
"""
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from application.services import llm_config
from domain.config.settings import settings
from infrastructure.config.db import get_session

router = APIRouter(prefix="/internal/jarvis", tags=["internal · jarvis"])


def _internal_auth(x_internal_key: Optional[str] = Header(default=None)) -> None:
    if not x_internal_key or not hmac.compare_digest(x_internal_key, settings.internal_api_key or ""):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clave interna inválida")


def _conversacional(agente: str, session: Session, centro_id: int):
    if agente == llm_config.VICTOR:
        from application.services.victor_agente import VictorAgente
        return VictorAgente(session, centro_id)
    if agente == llm_config.AURA:
        from application.services.aura_agente import AuraAgente
        return AuraAgente(session, centro_id)
    if agente == llm_config.GESTOR:
        from application.services.gestor_agente import GestorAgente
        return GestorAgente(session, centro_id)
    return None


class ContextoIn(BaseModel):
    centro_id: int
    telefono: str = ""
    simular: bool = False             # chat de entrenamiento: sin datos reales
    escenario: Optional[dict] = None


class HerramientaIn(BaseModel):
    centro_id: int
    telefono: str = ""
    nombre: str
    args: dict = Field(default_factory=dict)
    verificaciones: list[str] = Field(default_factory=list)
    simular: bool = False


@router.post("/{agente}/contexto", dependencies=[Depends(_internal_auth)])
def contexto(agente: str, body: ContextoIn, session: Session = Depends(get_session)) -> dict:
    if agente == llm_config.ALEX:
        from application.services.agente_service import AgenteService
        return AgenteService(session).contexto_operador(body.centro_id, body.telefono,
                                                        simular=body.simular, escenario=body.escenario)
    a = _conversacional(agente, session, body.centro_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Agente sin operador de Jarvis: {agente}")
    return {"system": a.system() + a._persona_extra(), "ejemplos": [], "historial": [],
            "tools": a.herramientas()}


@router.post("/{agente}/herramienta", dependencies=[Depends(_internal_auth)])
def herramienta(agente: str, body: HerramientaIn, session: Session = Depends(get_session)) -> dict:
    if agente == llm_config.ALEX:
        from application.services.agente_service import AgenteService
        resultado = AgenteService(session).herramienta_operador(
            body.centro_id, body.telefono, body.nombre, body.args, body.verificaciones,
            simular=body.simular)
        return {"resultado": resultado, "extra": {}}
    a = _conversacional(agente, session, body.centro_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Agente sin operador de Jarvis: {agente}")
    if body.nombre not in {t["function"]["name"] for t in a.herramientas()}:
        import json
        return {"resultado": json.dumps({"error": "herramienta_no_permitida", "herramienta": body.nombre}),
                "extra": {}}
    resultado = a.ejecutar(body.nombre, body.args or {})
    # Lo que el agente acumula al ejecutar (Victor: accionesPendientes) vuelve a Jarvis, que
    # lo junta y lo devuelve con la respuesta: la web lo entrega igual que antes.
    return {"resultado": resultado, "extra": a.extra()}
