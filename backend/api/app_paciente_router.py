"""🧿 MEMBRANA PACIENTE — gateway de la app nativa del paciente.

Prefix `/app/pacientes/me/...`: ningún endpoint lleva `paciente_id` en la URL — todo se
scopea implícitamente por el JWT del paciente (current.paciente_id/centro_id), lo que
elimina por construcción la clase de IDOR que un `paciente_id` en el path invitaría.

Reutiliza la lógica de consulta YA auditada y en producción para el personal
(pacientes_router.py, disponibilidad_service.py, produccion_service.py) — cero
duplicación de reglas de negocio (CLAUDE.md R4).
"""
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select
from starlette.background import BackgroundTask

from api.paciente_auth_deps import CurrentPaciente, get_current_paciente
from api.paciente_helper import _get_paciente
from api.pacientes_router import _actos_data, _edad, _presupuestos_data
from application.services.disponibilidad_service import DisponibilidadService
from application.services.produccion_service import ProduccionService
from domain.models.agenda import Agenda, EstadoCita, Gabinete
from domain.models.core import Centro, Cita, ColaboradorCentro, RazonSocial
from domain.models.economico import TratamientoRealizado
from infrastructure.config.db import get_session
from infrastructure.events import emit
from infrastructure.realtime import bus
from infrastructure.external_apis.documento_paciente_pdf import (
    render_factura_pdf, render_justificante_pdf,
)

router = APIRouter(prefix="/app/pacientes/me", tags=["app paciente · gateway"])

# Filiación reducida a lo que un paciente puede ver de sí mismo: sin notas internas de
# doctor ni campos libres de uso administrativo (esos son de _CORE_FIELDS, no de aquí).
_PERFIL_FIELDS = (
    "num_historia", "nombre", "apellidos", "nif", "fecha_nacimiento", "direccion", "cp",
    "telefono_fijo", "telefono_movil", "email",
    "responsable_nombre", "responsable_parentesco",
    "grupo_sanguineo", "peso", "altura", "medico_cabecera", "tel_medico", "especialista",
)


def _clinic_dto(session: Session, centro_id: int) -> dict:
    centro = session.get(Centro, centro_id)
    rs = session.exec(select(RazonSocial).where(RazonSocial.centro_id == centro_id)).first()
    return {
        "nombre": centro.nombre if centro else None,
        "direccion": centro.direccion if centro else None,
        "poblacion": centro.poblacion if centro else None,
        "telefono": centro.telefono if centro else None,
        "cif": rs.cif if rs else None,
    }


# ───────────────────────── perfil ─────────────────────────
@router.get("/perfil")
def perfil(current: CurrentPaciente = Depends(get_current_paciente),
           session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, current.centro_id, current.paciente_id)
    data = {f: getattr(p, f) for f in _PERFIL_FIELDS}
    data["id"] = p.id
    data["edad"] = _edad(p.fecha_nacimiento)
    return data


# ───────────────────────── tratamientos realizados ─────────────────────────
@router.get("/tratamientos")
def tratamientos(current: CurrentPaciente = Depends(get_current_paciente),
                 session: Session = Depends(get_session)) -> dict:
    return _actos_data(session, current.centro_id, current.paciente_id)


# ───────────────────────── presupuestos ─────────────────────────
@router.get("/presupuestos")
def presupuestos(current: CurrentPaciente = Depends(get_current_paciente),
                 session: Session = Depends(get_session)) -> dict:
    return _presupuestos_data(session, current.centro_id, current.paciente_id)


# ───────────────────────── agenda: huecos + solicitar cita ─────────────────────────
@router.get("/huecos")
def huecos(dias: int = 14, current: CurrentPaciente = Depends(get_current_paciente),
          session: Session = Depends(get_session)) -> dict:
    return {"data": DisponibilidadService(session).huecos(current.centro_id, dias=dias)}


class SolicitarCitaIn(BaseModel):
    fecha: date
    hora: str
    colaborador_id: Optional[int] = None
    gabinete_id: Optional[int] = None
    motivo: Optional[str] = None


@router.post("/citas/solicitar", status_code=status.HTTP_201_CREATED)
def solicitar_cita(data: SolicitarCitaIn, current: CurrentPaciente = Depends(get_current_paciente),
                   session: Session = Depends(get_session)) -> dict:
    """El paciente propone, el profesional dispone (ARQUITECTURA-ORGANISMO.md §5.B):
    crea la cita en estado 'solicitada', NUNCA auto-confirmada."""
    p = _get_paciente(session, current.centro_id, current.paciente_id)
    agenda = session.exec(
        select(Agenda).where(Agenda.centro_id == current.centro_id, Agenda.activo == True)  # noqa: E712
        .order_by(Agenda.id)
    ).first()
    if not agenda:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El centro no tiene agenda activa")
    estado = session.exec(
        select(EstadoCita).where(
            EstadoCita.centro_id == current.centro_id, EstadoCita.agenda_id == agenda.id,
            EstadoCita.codigo == "solicitada",
        )
    ).first()
    if not estado:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Estado 'solicitada' no configurado")

    # El paciente elige de /huecos, pero no nos fiamos del cliente: colaborador/gabinete
    # deben pertenecer de verdad al centro (mismo patrón que agenda_router.crear_cita
    # debería tener — aquí sí lo exigimos desde el día 1).
    if data.colaborador_id is not None:
        pertenece = session.exec(
            select(ColaboradorCentro).where(
                ColaboradorCentro.colaborador_id == data.colaborador_id,
                ColaboradorCentro.centro_id == current.centro_id,
            )
        ).first()
        if not pertenece:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Colaborador no pertenece a este centro")
    if data.gabinete_id is not None:
        gabinete = session.get(Gabinete, data.gabinete_id)
        if not gabinete or gabinete.centro_id != current.centro_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Gabinete no pertenece a este centro")

    cita = Cita(
        centro_id=current.centro_id, agenda_id=agenda.id, estado_id=estado.id,
        paciente_id=p.id, colaborador_id=data.colaborador_id, gabinete_id=data.gabinete_id,
        fecha=data.fecha, hora=data.hora,
        nombre=p.nombre, apellidos=p.apellidos, telefono_movil=p.telefono_movil,
        notas=(data.motivo or "Solicitada desde la app del paciente"),
    )
    session.add(cita)
    session.commit()
    session.refresh(cita)
    emit("cita.solicitada", {"cita_id": cita.id, "centro_id": current.centro_id, "paciente_id": p.id,
                             "fecha": cita.fecha.isoformat(), "hora": cita.hora})
    return {"id": cita.id, "fecha": cita.fecha.isoformat(), "hora": cita.hora, "estado": estado.nombre}


# ───────────────────────── facturas ─────────────────────────
@router.get("/facturas")
def listar_facturas(current: CurrentPaciente = Depends(get_current_paciente),
                    session: Session = Depends(get_session)) -> dict:
    rows = ProduccionService(session).patient_treatments(current.centro_id, current.paciente_id)["data"]
    por_factura: dict[str, dict] = {}
    for r in rows:
        num = r.get("facturaNumero")
        if not num:
            continue
        f = por_factura.setdefault(num, {"numero": num, "fecha": r["fecha"], "total": 0.0})
        f["total"] = round(f["total"] + r["neto"], 2)
    return {"facturas": sorted(por_factura.values(), key=lambda x: x["fecha"] or "", reverse=True)}


def _pdf_response(path: Path, filename: str):
    # Borra el PDF temporal en cuanto la respuesta se ha enviado.
    return FileResponse(str(path), media_type="application/pdf", filename=filename,
                        background=BackgroundTask(os.unlink, str(path)))


@router.get("/facturas/{numero}/pdf")
def factura_pdf(numero: str, current: CurrentPaciente = Depends(get_current_paciente),
                session: Session = Depends(get_session)):
    svc = ProduccionService(session)
    result = svc.patient_treatments(current.centro_id, current.paciente_id)
    lineas = [r for r in result["data"] if r.get("facturaNumero") == numero]
    if not lineas:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    total = round(sum(l["neto"] for l in lineas), 2)
    with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = Path(tmp.name)
    render_factura_pdf(pdf_path, centro=_clinic_dto(session, current.centro_id),
                       paciente=result["paciente"], numero=numero, lineas=lineas, total=total)
    return _pdf_response(pdf_path, f"factura_{numero}.pdf")


# ───────────────────────── justificantes ─────────────────────────
@router.get("/justificantes/{acto_id}/pdf")
def justificante_pdf(acto_id: int, current: CurrentPaciente = Depends(get_current_paciente),
                     session: Session = Depends(get_session)):
    acto = session.get(TratamientoRealizado, acto_id)
    if not acto or acto.paciente_id != current.paciente_id or acto.centro_id != current.centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Acto no encontrado")
    p = _get_paciente(session, current.centro_id, current.paciente_id)
    actos = _actos_data(session, current.centro_id, current.paciente_id)["actos"]
    dto = next((a for a in actos if a["id"] == acto_id), None)
    if not dto or not acto.fecha_inicio:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Acto no encontrado")
    with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = Path(tmp.name)
    render_justificante_pdf(
        pdf_path, centro=_clinic_dto(session, current.centro_id),
        paciente={"nombre": f"{p.nombre or ''} {p.apellidos or ''}".strip(), "nif": p.nif},
        fecha=acto.fecha_inicio, concepto=dto["tratamiento"], doctor=dto["doctor"],
    )
    return _pdf_response(pdf_path, f"justificante_{acto_id}.pdf")


# ───────────────────────── TIEMPO REAL (SSE) ─────────────────────────
# Eventos que le interesan a ESTA app de paciente. El bus reparte por centro; aquí
# filtramos ademas por paciente_id (el paciente solo ve lo suyo) y por tipo.
_EVENTOS_PACIENTE = {
    "cita.creada", "cita.actualizada", "cita.movida", "cita.anulada",
    "presupuesto.creado", "factura.emitida",
}


@router.get("/stream")
async def stream(current: CurrentPaciente = Depends(get_current_paciente)) -> StreamingResponse:
    """SSE: empuja al movil los cambios que le afectan a este paciente (sus citas, sus
    presupuestos, sus facturas) mientras la app este abierta. Heartbeat cada 15s para que
    los proxies no corten la conexion. La app, al (re)conectar, hace un refetch completo
    — este stream avisa de que ALGO cambio, no transporta el estado."""
    async def gen():
        q = await bus.subscribe(current.centro_id)
        try:
            yield ": ok\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if ev.get("tipo") not in _EVENTOS_PACIENTE:
                    continue
                if ev.get("paciente_id") != current.paciente_id:
                    continue
                yield f"event: {ev['tipo']}\ndata: {json.dumps(ev)}\n\n"
        finally:
            bus.unsubscribe(current.centro_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
