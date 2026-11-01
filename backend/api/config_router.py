"""Endpoints de configuración (capa de interfaz).

Leer la config efectiva de un sistema (cualquier usuario autenticado del centro)
y escribirla (requiere permiso fino `config.editar`). Toda escritura se audita.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlmodel import Session

from api.auth_deps import CurrentUser, get_current_centro, get_current_user, require_permission
from application.services.auth_service import AuthService
from application.services.config_service import ConfigService
from infrastructure.config.db import get_session

router = APIRouter(prefix="/config", tags=["config"])


class ConfigSet(BaseModel):
    clave: str
    valor: Any = None
    sistema: Optional[str] = None


@router.get("")
def get_config(
    sistema: Optional[str] = None,
    centro_id: int = Depends(get_current_centro),
    _user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Config efectiva (global ⊕ centro ⊕ sistema) para el centro activo."""
    valores = ConfigService(session).for_scope(centro_id=centro_id, sistema=sistema)
    return {"centro_id": centro_id, "sistema": sistema, "valores": valores}


@router.put("")
def set_config(
    data: ConfigSet,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    """Upsert de una clave en el ámbito del centro (+ sistema opcional). Auditado."""
    svc = ConfigService(session)
    row = svc.set(data.clave, data.valor, centro_id=centro_id, sistema=data.sistema)
    AuthService(session).audit(
        "config.set", usuario_id=user.usuario_id, centro_id=centro_id,
        recurso=f"config:{data.sistema or '*'}:{data.clave}", detalle={"valor": data.valor},
        ip=request.client.host if request.client else None,
    )
    return {"id": row.id, "clave": row.clave, "valor": row.valor,
            "centro_id": row.centro_id, "sistema": row.sistema}
