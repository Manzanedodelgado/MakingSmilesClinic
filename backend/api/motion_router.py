"""MOTION (Automatizaciones) — endpoints del módulo (capa de interfaz).

Reglas = catálogo de disparadores con su fila en `plantillas_mensaje` (CONFIG = verdad);
maestro = `agente.alex.automatizacion` (la MISMA clave que Config › IA's › Alex);
estadísticas derivadas de `envios_automaticos` (cero duplicación).
Permisos: Motion es superficie de comunicación → comunicacion.ver / comunicacion.editar.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.audit_helper import _audit
from application.services.automatizacion_service import AutomatizacionService
from application.services.automatizacion_triggers import CATALOGO, CATALOGO_IDX
from domain.services.whatsapp_flujos import FLUJOS_INFO
from infrastructure.config.db import get_session

router = APIRouter(prefix="/motion", tags=["motion · automatizaciones"])

VER = "comunicacion.ver"
EDITAR = "comunicacion.editar"


def _svc(session: Session) -> AutomatizacionService:
    return AutomatizacionService(session)


# ─────────────────────── CATÁLOGO / REGLAS ───────────────────────
@router.get("/catalogo")
def catalogo(user: CurrentUser = Depends(require_permission(VER))) -> dict:
    """Catálogo de disparadores (para selects: Editor, Config › Plantillas)."""
    return {"data": [{"disparador": c["disparador"], "nombre": c["nombre"],
                      "grupo": c["grupo"], "descripcion": c["descripcion"]} for c in CATALOGO]}


@router.get("/reglas")
def reglas(centro_id: int = Depends(get_current_centro),
           user: CurrentUser = Depends(require_permission(VER)),
           session: Session = Depends(get_session)) -> dict:
    return _svc(session).reglas(centro_id)


class ReglaIn(BaseModel):
    activo: bool


@router.patch("/reglas/{disparador}")
def toggle_regla(disparador: str, data: ReglaIn, request: Request,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission(EDITAR)),
                 session: Session = Depends(get_session)) -> dict:
    try:
        res = _svc(session).set_regla(centro_id, disparador, data.activo, user.usuario_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    _audit(session, user, centro_id, "toggle", f"motion/regla/{disparador}", request,
           "ON" if data.activo else "OFF")
    return res


class PlantillaReglaIn(BaseModel):
    nombre: Optional[str] = None
    cuerpo: Optional[str] = None
    tipo: Optional[str] = None
    opciones: Optional[Any] = None


@router.put("/reglas/{disparador}/plantilla")
def guardar_plantilla(disparador: str, data: PlantillaReglaIn, request: Request,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission(EDITAR)),
                      session: Session = Depends(get_session)) -> dict:
    try:
        res = _svc(session).guardar_plantilla_regla(
            centro_id, disparador, data.model_dump(), user.usuario_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    _audit(session, user, centro_id, "guardar", f"motion/plantilla/{disparador}", request)
    return res


# ─────────────────────── MAESTRO ───────────────────────
@router.get("/maestro")
def maestro(centro_id: int = Depends(get_current_centro),
            user: CurrentUser = Depends(require_permission(VER)),
            session: Session = Depends(get_session)) -> dict:
    svc = _svc(session)
    return {"activo": svc.maestro(centro_id), "whatsapp_activo": svc.whatsapp_activo(centro_id)}


@router.put("/maestro")
def set_maestro(data: ReglaIn, request: Request,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission(EDITAR)),
                session: Session = Depends(get_session)) -> dict:
    activo = _svc(session).set_maestro(centro_id, data.activo)
    _audit(session, user, centro_id, "maestro", "motion/maestro", request,
           "ON" if activo else "OFF")
    return {"activo": activo}


# ─────────────────────── PREVIEW / FLUJOS ───────────────────────
class PreviewIn(BaseModel):
    disparador: Optional[str] = None   # None = todos los activos


@router.post("/preview")
def preview(data: PreviewIn,
            centro_id: int = Depends(get_current_centro),
            user: CurrentUser = Depends(require_permission(VER)),
            session: Session = Depends(get_session)) -> dict:
    """Qué se enviaría AHORA (sin enviar ni registrar nada). Con `disparador`, hace el
    preview de ESE aunque esté apagado — para probar una regla antes de encenderla."""
    if data.disparador and data.disparador not in CATALOGO_IDX:
        # Sin esto, un disparador mal escrito devolvería "0 candidatos" en vez de avisar.
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Disparador desconocido: {data.disparador}")
    return _svc(session).ejecutar(centro_id, enviar=False, solo=data.disparador)


@router.get("/flujos")
def flujos(user: CurrentUser = Depends(require_permission(VER))) -> dict:
    """Flujos conversacionales reales de WhatsApp (máquina de estados del backend)."""
    return {"data": FLUJOS_INFO}
