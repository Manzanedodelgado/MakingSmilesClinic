"""VOICEBOT — endpoints del canal de voz (capa de interfaz). Solo BBDD nueva.

Los consume la pasarela telefónica (AGI/Asterisk, Twilio, Zadarma): config de voz,
salud, y procesar cada turno (texto transcrito → respuesta del agente para TTS).
Más historial y métricas. Permisos: comunicacion.ver / comunicacion.editar.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlmodel import Session

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from application.services.auth_service import AuthService
from application.services.voicebot_service import VoicebotService
from infrastructure.config.db import get_session

router = APIRouter(prefix="/comunicacion/voicebot", tags=["comunicación · voicebot"])

VER = "comunicacion.ver"
EDITAR = "comunicacion.editar"


def _svc(session: Session) -> VoicebotService:
    return VoicebotService(session)


@router.get("/voice-config")
def voice_config(centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission(VER)),
                 session: Session = Depends(get_session)) -> dict:
    return _svc(session).voice_config(centro_id)


@router.get("/health")
def health(centro_id: int = Depends(get_current_centro),
           user: CurrentUser = Depends(require_permission(VER)),
           session: Session = Depends(get_session)) -> dict:
    return _svc(session).health(centro_id)


class TurnoIn(BaseModel):
    telefono: str
    texto: str
    duracion_seg: Optional[int] = None


@router.post("/turno")
def turno(data: TurnoIn, request: Request,
          centro_id: int = Depends(get_current_centro),
          user: CurrentUser = Depends(require_permission(EDITAR)),
          session: Session = Depends(get_session)) -> dict:
    res = _svc(session).procesar_turno(centro_id, data.telefono, data.texto, data.duracion_seg)
    AuthService(session).audit("voicebot.turno", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso="comunicacion/voicebot",
                               ip=request.client.host if request.client else None)
    return res


@router.get("/historial")
def historial(paciente_id: Optional[int] = None, limit: int = 50,
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission(VER)),
              session: Session = Depends(get_session)) -> dict:
    return {"data": _svc(session).historial(centro_id, paciente_id, limit)}


@router.get("/stats")
def stats(dias: int = 30,
          centro_id: int = Depends(get_current_centro),
          user: CurrentUser = Depends(require_permission(VER)),
          session: Session = Depends(get_session)) -> dict:
    return _svc(session).stats(centro_id, dias)
