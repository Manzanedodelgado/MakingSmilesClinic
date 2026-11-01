"""🧿 MEMBRANA PACIENTE — login por código OTP (WhatsApp, fallback email).

Sustituye a los dos endpoints falsos eliminados el 19-jul-2026 (`/apps/auth/login` y
`/auth/paciente/login-codigo`, ambos bypasses confirmados: aceptaban cualquier código).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session

from application.services.paciente_auth_service import (
    PacienteAuthError, PacienteAuthNombreRequerido, PacienteAuthService,
)
from infrastructure.config.db import get_session

router = APIRouter(prefix="/app/auth", tags=["app paciente · auth"])


class SolicitarCodigoIn(BaseModel):
    identificador: str  # teléfono móvil o email del paciente
    # Si el teléfono lo comparten varios pacientes, obligatorio desde el
    # primer paso: sin saber QUIÉN eres no se envía ningún código.
    nombre_apellidos: str | None = None


class VerificarCodigoIn(BaseModel):
    identificador: str
    codigo: str
    # Solo hace falta cuando el teléfono está duplicado entre varios pacientes activos
    # (ver PacienteAuthNombreRequerido) — la app lo pide en un segundo paso, no de entrada.
    nombre_apellidos: str | None = None


@router.post("/solicitar-codigo")
def solicitar_codigo(data: SolicitarCodigoIn, request: Request, session: Session = Depends(get_session)) -> dict:
    ip = request.client.host if request.client else None
    try:
        PacienteAuthService(session).solicitar_codigo(
            data.identificador.strip(),
            nombre_apellidos=(data.nombre_apellidos or "").strip() or None, ip=ip)
    except PacienteAuthNombreRequerido as exc:
        # 428 igual que en verificar: la app muestra el campo de nombre
        # ANTES de que se envíe ningún código.
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, str(exc))
    except PacienteAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
    # Respuesta SIEMPRE igual: no revela si el identificador existe (anti-enumeración).
    return {"ok": True}


@router.post("/verificar-codigo")
def verificar_codigo(data: VerificarCodigoIn, request: Request, session: Session = Depends(get_session)) -> dict:
    ip = request.client.host if request.client else None
    try:
        return PacienteAuthService(session).verificar_codigo(
            data.identificador.strip(), data.codigo.strip(),
            nombre_apellidos=(data.nombre_apellidos or "").strip() or None, ip=ip,
        )
    except PacienteAuthNombreRequerido as exc:
        # 428 Precondition Required: el código es correcto, falta un dato más (nombre)
        # para completar el login — distinto de 401 (código erróneo), la app lo usa para
        # mostrar el campo de nombre en vez de un error genérico.
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, str(exc))
    except PacienteAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
