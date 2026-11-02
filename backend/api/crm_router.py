"""CRM — endpoints. Primer bloque: reactivación de pacientes inactivos / revisión vencida."""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from application.services.crm_service import CrmService
from infrastructure.config.db import get_session

router = APIRouter(prefix="/crm", tags=["crm"])
VER = "pacientes.ver"   # el CRM muestra ficha/contacto de pacientes → mismo permiso


@router.get("/inactivos")
def inactivos(meses: int = 12, centro_id: int = Depends(get_current_centro),
              _u: CurrentUser = Depends(require_permission(VER)),
              session: Session = Depends(get_session)) -> dict:
    """Pacientes activos sin volver desde hace `meses` (con actividad previa), a reactivar."""
    return CrmService(session).inactivos(centro_id, meses=meses)


@router.get("/pipeline")
def pipeline(centro_id: int = Depends(get_current_centro),
             _u: CurrentUser = Depends(require_permission(VER)),
             session: Session = Depends(get_session)) -> dict:
    """Embudo de presupuestos: conversión + presupuestos colgados (presentados sin cerrar) a perseguir."""
    return CrmService(session).pipeline(centro_id)
