"""INICIO — el pulso de la clínica (una sola llamada, todo lo que necesita atención)."""
from datetime import date
from typing import Optional

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlmodel import Session

from api.audit_helper import _audit
from api.auth_deps import CurrentUser, get_current_centro, get_current_user, require_permission
from application.services.caja_service import Aplicacion, CajaService
from application.services.auth_service import AuthService
from application.services.inicio_paciente_service import InicioPacienteService
from application.services.pulso_service import PulsoService
from infrastructure.config.db import get_session

router = APIRouter(prefix="/inicio", tags=["inicio · pulso"])


@router.get("/pulso")
def pulso(centro_id: int = Depends(get_current_centro),
          user: CurrentUser = Depends(get_current_user),
          session: Session = Depends(get_session)) -> dict:
    """Todo lo pendiente, ya filtrado por lo que este usuario tiene derecho a ver.

    No exige un permiso concreto: cualquiera con acceso al centro entra, pero cada bloque
    se calcula sólo si tiene el permiso de su área. Así el panel nunca es una puerta
    trasera a datos de un área cerrada para quien lo mira."""
    permisos = AuthService(session).permisos_de(user.usuario_id, centro_id)
    return PulsoService(session, centro_id, permisos).pulso()


@router.get("/citas")
def citas(fecha: Optional[date] = Query(None, description="Día (por defecto, hoy)"),
          agenda_id: Optional[int] = Query(None),
          colaborador_id: Optional[int] = Query(None),
          gabinete_id: Optional[int] = Query(None),
          estado_id: Optional[int] = Query(None),
          tipo_cita_id: Optional[int] = Query(None),
          centro_id: int = Depends(get_current_centro),
          user: CurrentUser = Depends(get_current_user),
          session: Session = Depends(get_session)) -> dict:
    """Citas de un día para el Cover Flow de Inicio, con filtros y las opciones de cada filtro.

    Mismo criterio de acceso que el pulso (citas.ver o pacientes.ver); sin él → permitido=false."""
    permisos = AuthService(session).permisos_de(user.usuario_id, centro_id)
    svc = PulsoService(session, centro_id, permisos)
    return svc.citas(fecha or svc.hoy, agenda_id=agenda_id, colaborador_id=colaborador_id,
                     gabinete_id=gabinete_id, estado_id=estado_id, tipo_cita_id=tipo_cita_id)


@router.get("/paciente/{paciente_id}")
def paciente(paciente_id: int,
             centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(get_current_user),
             session: Session = Depends(get_session)) -> dict:
    """Todo lo del paciente de agenda para gestionarlo desde Inicio: sus citas, sus
    automatizaciones y el estado de su flujo de WhatsApp. Cada sección con su permiso."""
    permisos = AuthService(session).permisos_de(user.usuario_id, centro_id)
    r = InicioPacienteService(session, centro_id, permisos).resumen(paciente_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return r


@router.get("/conversacion")
def conversacion(paciente_id: int | None = Query(None), telefono: str | None = Query(None),
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(get_current_user),
                 session: Session = Depends(get_session)) -> dict:
    """WhatsApp del paciente de agenda (por ficha o, si la cita no tiene ficha, por teléfono)."""
    permisos = AuthService(session).permisos_de(user.usuario_id, centro_id)
    return InicioPacienteService(session, centro_id, permisos).conversacion(paciente_id, telefono)


class AplicacionIn(BaseModel):
    importe: Decimal
    deuda_id: Optional[int] = None
    acto_id: Optional[int] = None


class CobroIn(BaseModel):
    forma_pago_id: int
    aplicaciones: list[AplicacionIn] = []
    fecha: Optional[date] = None
    importe: Optional[Decimal] = None          # total del pago; el sobrante queda de saldo
    presupuesto_id: Optional[int] = None       # saldo asociado a un presupuesto aceptado


@router.get("/paciente/{paciente_id}/caja")
def caja(paciente_id: int,
         centro_id: int = Depends(get_current_centro),
         user: CurrentUser = Depends(require_permission("pacientes.ver")),
         session: Session = Depends(get_session)) -> dict:
    """Lo que el paciente tiene pendiente de cobro (cargos abiertos + actos sin cargo) y las
    formas de pago de caja (catálogo único `formas_pago`)."""
    return CajaService(session, centro_id).estado(paciente_id)


@router.post("/paciente/{paciente_id}/cobro", status_code=status.HTTP_201_CREATED)
def cobro(paciente_id: int, data: CobroIn, request: Request,
          centro_id: int = Depends(get_current_centro),
          user: CurrentUser = Depends(require_permission("pacientes.editar")),
          session: Session = Depends(get_session)) -> dict:
    r = CajaService(session, centro_id).cobrar(
        paciente_id, data.forma_pago_id, data.fecha or date.today(),
        [Aplicacion(importe=a.importe, deuda_id=a.deuda_id, acto_id=a.acto_id) for a in data.aplicaciones],
        importe=data.importe, presupuesto_id=data.presupuesto_id)
    _audit(session, user, centro_id, "pagos.cobrar", f"pago:{r['pago_id']}", request,
           {"paciente_id": paciente_id, "importe": r["importe"], "forma_pago": r["forma_pago"],
            "conceptos": r["conceptos"], "presupuesto_id": r["presupuesto_id"]})
    return r
