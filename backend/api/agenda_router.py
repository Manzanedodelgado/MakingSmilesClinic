"""AGENDA — citas del centro (vista calendario). Solo BBDD nueva (makingsmiles).

Lee/escribe la tabla `citas` resolviendo estado (color), tipo de cita, gabinete,
colaborador y paciente. Lectura: permiso citas.ver · escritura: citas.editar (auditada).
"""
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from sqlalchemy import or_
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.audit_helper import _audit
from api.colaborador_helper import colaboradores_activos_rows
from application.services.auth_service import AuthService
from application.services.config_service import ConfigService
from application.services.disponibilidad_service import DisponibilidadService, estado_id_por_codigo
from domain.models.agenda import Agenda, BloqueoAgenda, ColaboradorHorario, EstadoCita, Gabinete, TipoCita
from domain.models.comunicacion import Conversacion
from domain.models.core import Centro, Cita, Colaborador, ColaboradorTipoCita, Paciente, RazonSocial
from infrastructure.external_apis.documento_paciente_pdf import render_justificante_pdf
from domain.models.documentos import Consentimiento, DocumentoFirmado
from domain.models.identidad import Usuario, UsuarioPeriodo
from infrastructure.config.db import get_session
from infrastructure.events import emit

router = APIRouter(prefix="/agenda", tags=["agenda · citas"])


def _colaboradores(session: Session, centro_id: int) -> list[dict]:
    rows = colaboradores_activos_rows(session, centro_id)
    return [{"id": c.id, "nombre": f"{u.nombre} {u.apellidos or ''}".strip(), "color": u.color} for c, u, _up in rows]


# ─────────────────────────── REFERENCIAS (para la pantalla) ───────────────────────────
@router.get("/referencias")
def referencias(agenda_id: Optional[int] = Query(None),
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("citas.ver")),
                session: Session = Depends(get_session)) -> dict:
    agendas = session.exec(select(Agenda).where(Agenda.centro_id == centro_id, Agenda.activo == True).order_by(Agenda.orden, Agenda.id)).all()  # noqa: E712
    ag_sel = next((a for a in agendas if a.id == agenda_id), None) or (agendas[0] if agendas else None)
    aid = ag_sel.id if ag_sel else None
    # Toda la config de agenda se filtra por la agenda seleccionada (gabinetes, estados, tipos).
    gstmt = select(Gabinete).where(Gabinete.centro_id == centro_id, Gabinete.activo == True)  # noqa: E712
    estmt = select(EstadoCita).where(EstadoCita.centro_id == centro_id)
    tstmt = select(TipoCita).where(TipoCita.centro_id == centro_id, TipoCita.activo == True)  # noqa: E712
    if aid is not None:
        gstmt = gstmt.where(Gabinete.agenda_id == aid)
        estmt = estmt.where(EstadoCita.agenda_id == aid)
        tstmt = tstmt.where(TipoCita.agenda_id == aid)
    gabs = session.exec(gstmt.order_by(Gabinete.nombre)).all()
    estados = session.exec(estmt.order_by(EstadoCita.orden)).all()
    tipos = session.exec(tstmt.order_by(TipoCita.nombre)).all()
    cfg = ConfigService(session)
    centro_hor = cfg.resolve("centro.horario", centro_id=centro_id, default={}) or {}
    festivos = cfg.resolve("centro.festivos", centro_id=centro_id, default=[]) or []
    # marco = horario del centro (dias); granularidad/vista = de la agenda elegida
    horario = {"dias": centro_hor.get("dias"),
               "intervalo": ag_sel.intervalo_min if ag_sel else None,
               "vistaDefecto": ag_sel.vista_defecto if ag_sel else None}
    # Bloqueos de agenda del centro (vacaciones, mantenimiento…) → impiden citar.
    bloqs = session.exec(select(BloqueoAgenda).where(BloqueoAgenda.centro_id == centro_id)).all()
    bloqueos = [{"fecha_inicio": b.fecha_inicio.isoformat(), "fecha_fin": b.fecha_fin.isoformat(),
                 "motivo": b.motivo, "colaborador_id": b.colaborador_id, "gabinete_id": b.gabinete_id} for b in bloqs]
    # Asignación gabinete↔doctor por día (de colaborador_horarios) → cabecera de columna.
    hors = session.exec(select(ColaboradorHorario).where(
        ColaboradorHorario.centro_id == centro_id, ColaboradorHorario.activo == True)).all()  # noqa: E712
    horarios = [{"colaborador_id": h.colaborador_id, "gabinete_id": h.gabinete_id, "dia_semana": h.dia_semana,
                 "hora_inicio": h.hora_inicio, "hora_fin": h.hora_fin} for h in hors]
    colaboradores = _colaboradores(session, centro_id)
    # Duración por (doctor, tipo de cita) — Config→Colaboradores→"Tiempos por tipo de cita".
    col_ids = [c["id"] for c in colaboradores]
    tipo_ids = [t.id for t in tipos]
    duraciones: list[dict] = []
    if col_ids and tipo_ids:
        dstmt = select(ColaboradorTipoCita).where(
            ColaboradorTipoCita.colaborador_id.in_(col_ids), ColaboradorTipoCita.tipo_cita_id.in_(tipo_ids))
        duraciones = [{"colaborador_id": d.colaborador_id, "tipo_cita_id": d.tipo_cita_id, "duracion_min": d.duracion_min}
                      for d in session.exec(dstmt).all()]
    return {"agendas": agendas, "gabinetes": gabs, "estados": estados, "tipos_cita": tipos,
            "colaboradores": colaboradores, "horario": horario, "duraciones": duraciones,
            "festivos": festivos, "bloqueos": bloqueos, "horarios": horarios}


# ─────────────────────────── BUSCAR PACIENTE (autocompletar) ───────────────────────────
@router.get("/pacientes/buscar")
def buscar_pacientes(q: str = Query(..., min_length=2),
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission("citas.ver")),
                     session: Session = Depends(get_session)) -> dict:
    like = f"%{q}%"
    rows = session.exec(
        select(Paciente).where(
            Paciente.centro_id == centro_id,
            or_(Paciente.nombre.ilike(like), Paciente.apellidos.ilike(like), Paciente.num_historia.ilike(f"{q}%")),
        ).order_by(Paciente.apellidos, Paciente.nombre).limit(15)
    ).all()
    return {"pacientes": [{"id": p.id, "nombre": p.nombre or "", "apellidos": p.apellidos or "",
                           "num_historia": p.num_historia, "telefono": p.telefono_movil or p.telefono_fijo} for p in rows]}


# ─────────────────────────── LISTAR CITAS (día o rango) ───────────────────────────
def _cita_dto(c: Cita, estados: dict, tipos: dict, pac: dict) -> dict:
    e = estados.get(c.estado_id)
    p = pac.get(c.paciente_id) if c.paciente_id else None
    # Nombre y apellidos SIEMPRE separados (inline en la cita o del paciente).
    nombre = c.nombre or (p["nombre"] if p else "") or ""
    apellidos = c.apellidos or (p["apellidos"] if p else "") or ""
    return {
        "id": c.id, "fecha": c.fecha.isoformat(), "hora": c.hora, "duracion_min": c.duracion_min or 30,
        "gabinete_id": c.gabinete_id, "colaborador_id": c.colaborador_id,
        "estado_id": c.estado_id, "estado_nombre": e["nombre"] if e else None, "estado_color": (e["color"] if e else None) or "#065AED",
        "tipo_cita_id": c.tipo_cita_id, "tipo_nombre": tipos.get(c.tipo_cita_id),
        "paciente_id": c.paciente_id, "nombre": nombre, "apellidos": apellidos,
        "num_historia": c.num_historia or (p["num_historia"] if p else None),
        "telefono": c.telefono_movil or (p["telefono"] if p else None),
        "notas": c.notas, "confirmada": c.confirmada,
    }


@router.get("/citas")
def listar_citas(
    fecha: Optional[date] = Query(None),
    desde: Optional[date] = Query(None),
    hasta: Optional[date] = Query(None),
    incluir_anuladas: bool = Query(False),
    agenda_id: Optional[int] = Query(None),
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("citas.ver")),
    session: Session = Depends(get_session),
) -> dict:
    stmt = select(Cita).where(Cita.centro_id == centro_id)
    if agenda_id:
        stmt = stmt.where(Cita.agenda_id == agenda_id)
    if fecha:
        stmt = stmt.where(Cita.fecha == fecha)
    elif desde and hasta:
        stmt = stmt.where(Cita.fecha >= desde, Cita.fecha <= hasta)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica fecha o desde+hasta")
    if not incluir_anuladas:
        anulada_id = estado_id_por_codigo(session, centro_id, "anulada", agenda_id)
        if anulada_id is not None:
            stmt = stmt.where(Cita.estado_id != anulada_id)
    citas = session.exec(stmt.order_by(Cita.hora)).all()

    estados = {e.id: {"nombre": e.nombre, "color": e.color} for e in session.exec(select(EstadoCita).where(EstadoCita.centro_id == centro_id)).all()}
    tipos = {t.id: t.nombre for t in session.exec(select(TipoCita).where(TipoCita.centro_id == centro_id)).all()}
    pac_ids = {c.paciente_id for c in citas if c.paciente_id}
    pac: dict = {}
    if pac_ids:
        for p in session.exec(select(Paciente).where(Paciente.id.in_(pac_ids))).all():
            pac[p.id] = {"nombre": p.nombre or "", "apellidos": p.apellidos or "",
                         "num_historia": p.num_historia, "telefono": p.telefono_movil or p.telefono_fijo}
    return {"citas": [_cita_dto(c, estados, tipos, pac) for c in citas]}


# ─────────────────────────── PANEL LATERAL (resumen del día) ───────────────────────────
def _nombres_pacientes(session: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    out: dict[int, str] = {}
    for p in session.exec(select(Paciente).where(Paciente.id.in_(ids))).all():
        out[p.id] = f"{p.nombre or ''} {p.apellidos or ''}".strip() or "—"
    return out


@router.get("/panel")
def panel(fecha: date = Query(...),
          agenda_id: Optional[int] = Query(None),
          centro_id: int = Depends(get_current_centro),
          user: CurrentUser = Depends(require_permission("citas.ver")),
          session: Session = Depends(get_session)) -> dict:
    """Widgets del panel derecho — todo de la BBDD nueva, scope al centro activo."""
    # 1) Confirmación de mañana: citas del día siguiente (no anuladas), cuántas confirmadas.
    manana = fecha + timedelta(days=1)
    stmt_m = select(Cita).where(Cita.centro_id == centro_id, Cita.fecha == manana)
    if agenda_id:
        stmt_m = stmt_m.where(Cita.agenda_id == agenda_id)
    anulada_id_m = estado_id_por_codigo(session, centro_id, "anulada", agenda_id)
    if anulada_id_m is not None:
        stmt_m = stmt_m.where(Cita.estado_id != anulada_id_m)
    citas_m = session.exec(stmt_m.order_by(Cita.hora)).all()
    pac_m = _nombres_pacientes(session, {c.paciente_id for c in citas_m if c.paciente_id})
    confirmacion = {
        "fecha": manana.isoformat(),
        "total": len(citas_m),
        "confirmadas": sum(1 for c in citas_m if c.confirmada),
        "citas": [{
            "id": c.id, "hora": c.hora,
            "nombre": (f"{c.nombre or ''} {c.apellidos or ''}".strip() or pac_m.get(c.paciente_id, "—")),
            "confirmada": c.confirmada,
        } for c in citas_m],
    }

    # 2) WhatsApp urgentes: conversaciones de WhatsApp abiertas etiquetadas como urgencia.
    wa = session.exec(select(Conversacion).where(
        Conversacion.centro_id == centro_id, Conversacion.canal == "whatsapp",
        Conversacion.estado == "abierta", Conversacion.tags.ilike("%urg%"),
    ).order_by(Conversacion.updated_at.desc())).all()
    pac_wa = _nombres_pacientes(session, {w.paciente_id for w in wa if w.paciente_id})
    whatsapp = {"total": len(wa), "items": [
        {"id": w.id, "paciente": pac_wa.get(w.paciente_id, "") if w.paciente_id else "",
         "telefono": w.telefono or "", "tags": w.tags or ""} for w in wa[:20]
    ]}

    # 3) Consentimientos pendientes de firma.
    cons = session.exec(select(Consentimiento).where(
        Consentimiento.centro_id == centro_id, Consentimiento.estado == "pendiente",
    ).order_by(Consentimiento.created_at.desc())).all()
    pac_c = _nombres_pacientes(session, {x.paciente_id for x in cons})
    consentimientos = {"total": len(cons), "items": [
        {"id": x.id, "paciente": pac_c.get(x.paciente_id, "—"), "tipo": x.tipo} for x in cons[:20]
    ]}

    # 4) Firmas de doctor pendientes (documentos_firmados sin firma del colaborador).
    #    documentos_firmados no tiene centro_id → se acota por el paciente del centro.
    firmas_rows = session.exec(
        select(DocumentoFirmado, Paciente)
        .join(Paciente, Paciente.id == DocumentoFirmado.paciente_id)
        .where(Paciente.centro_id == centro_id, DocumentoFirmado.firmado_colaborador == False)  # noqa: E712
        .order_by(DocumentoFirmado.fecha.desc())
    ).all()
    firmas = {"total": len(firmas_rows), "items": [
        {"id": d.id, "paciente": f"{p.nombre or ''} {p.apellidos or ''}".strip() or "—",
         "descripcion": d.descripcion or d.tipo_doc or "Documento"} for d, p in firmas_rows[:20]
    ]}

    return {"confirmacion": confirmacion, "whatsapp": whatsapp,
            "consentimientos": consentimientos, "firmas": firmas}


# ─────────────────────────── HUECOS LIBRES (disponibilidad) ───────────────────────────
@router.get("/huecos")
def huecos(agenda_id: Optional[int] = Query(None),
           colaborador_id: Optional[int] = Query(None),
           dias: int = Query(7, ge=1, le=30),
           duracion_min: int = Query(30, ge=5, le=240),
           centro_id: int = Depends(get_current_centro),
           user: CurrentUser = Depends(require_permission("citas.ver")),
           session: Session = Depends(get_session)) -> dict:
    """Huecos libres próximos para ofrecer/crear cita (agenda + colaborador opcionales)."""
    return {"data": DisponibilidadService(session).huecos(
        centro_id, agenda_id=agenda_id, colaborador_id=colaborador_id,
        dias=dias, duracion_min=duracion_min)}


# ─────────────────────────── CREAR / EDITAR / ANULAR ───────────────────────────


class CitaIn(BaseModel):
    fecha: date
    hora: str
    duracion_min: Optional[int] = 30
    agenda_id: Optional[int] = None
    gabinete_id: Optional[int] = None
    colaborador_id: Optional[int] = None
    estado_id: Optional[int] = None
    tipo_cita_id: Optional[int] = None
    paciente_id: Optional[int] = None
    nombre: Optional[str] = None
    apellidos: Optional[str] = None
    telefono_movil: Optional[str] = None
    num_historia: Optional[str] = None
    notas: Optional[str] = None
    email: Optional[str] = None


_EDIT = {"fecha", "hora", "duracion_min", "agenda_id", "gabinete_id", "colaborador_id", "estado_id",
         "tipo_cita_id", "paciente_id", "nombre", "apellidos", "telefono_movil", "num_historia", "notas", "email"}


def _v(x):
    """Valor serializable para el registro de modificaciones."""
    return x.isoformat() if hasattr(x, "isoformat") else x


def _marcar_modificacion(c, cambia_estado: bool) -> None:
    """Una cita es UNA fila (id_cita único): se actualiza y se apunta cuándo cambió."""
    ahora = datetime.now()
    c.fecha_hora_modificacion = ahora
    if cambia_estado:
        c.fecha_hora_estado = ahora


@router.post("/citas", status_code=201)
def crear_cita(data: CitaIn, request: Request, centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("citas.editar")), session: Session = Depends(get_session)) -> dict:
    if data.paciente_id is not None:
        pac = session.get(Paciente, data.paciente_id)
        if not pac or pac.centro_id != centro_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Paciente no encontrado")
    body = data.model_dump()
    # Sin agenda_id la cita queda invisible para el calendario (que siempre filtra por
    # agenda_id) — si el cliente no lo manda, cae a la única/primera agenda del centro.
    if body["agenda_id"] is None:
        primera = session.exec(select(Agenda).where(Agenda.centro_id == centro_id).order_by(Agenda.orden, Agenda.id)).first()
        body["agenda_id"] = primera.id if primera else None
    if body["estado_id"] is None:
        body["estado_id"] = estado_id_por_codigo(session, centro_id, "planificada", body["agenda_id"])
    c = Cita(centro_id=centro_id, **body)
    session.add(c); session.commit(); session.refresh(c)
    cid = c.id
    _audit(session, user, centro_id, "agenda.cita.crear", f"cita:{cid}", request, {"fecha": data.fecha.isoformat(), "hora": data.hora})
    emit("cita.creada", {"cita_id": cid, "centro_id": centro_id, "paciente_id": c.paciente_id,
                         "fecha": data.fecha.isoformat(), "hora": data.hora})
    return {"id": cid}


@router.put("/citas/{cita_id}")
def editar_cita(cita_id: int, data: CitaIn, request: Request, centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("citas.editar")), session: Session = Depends(get_session)) -> dict:
    c = session.get(Cita, cita_id)
    if not c or c.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")
    if data.paciente_id is not None:
        pac = session.get(Paciente, data.paciente_id)
        if not pac or pac.centro_id != centro_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Paciente no encontrado")
    cambios = {}
    for k, v in data.model_dump().items():
        # agenda_id/estado_id: None significa "no lo mandó el cliente", no "bórralo" —
        # nulificarlos aquí repetiría el bug de citas huérfanas de su agenda.
        # email: el listado no lo devuelve, así que un None al editar tampoco lo borra.
        if k in ("agenda_id", "estado_id", "email") and v is None:
            continue
        if k in _EDIT and getattr(c, k) != v:
            cambios[k] = {"antes": _v(getattr(c, k)), "despues": _v(v)}
            setattr(c, k, v)
    _marcar_modificacion(c, "estado_id" in cambios)
    session.add(c); session.commit()
    _audit(session, user, centro_id, "agenda.cita.editar", f"cita:{cita_id}", request, {"cambios": cambios})
    emit("cita.actualizada", {"cita_id": cita_id, "centro_id": centro_id, "paciente_id": c.paciente_id})
    return {"id": cita_id}


class MoverIn(BaseModel):
    fecha: date
    hora: str
    gabinete_id: Optional[int] = None


@router.put("/citas/{cita_id}/mover")
def mover_cita(cita_id: int, data: MoverIn, request: Request, centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("citas.editar")), session: Session = Depends(get_session)) -> dict:
    c = session.get(Cita, cita_id)
    if not c or c.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")
    antes = {"fecha": _v(c.fecha), "hora": c.hora, "gabinete_id": c.gabinete_id}
    c.fecha, c.hora = data.fecha, data.hora
    if data.gabinete_id is not None:
        c.gabinete_id = data.gabinete_id
    _marcar_modificacion(c, False)
    session.add(c); session.commit()
    _audit(session, user, centro_id, "agenda.cita.mover", f"cita:{cita_id}", request,
           {"antes": antes, "despues": {"fecha": _v(c.fecha), "hora": c.hora, "gabinete_id": c.gabinete_id}})
    emit("cita.movida", {"cita_id": cita_id, "centro_id": centro_id, "paciente_id": c.paciente_id,
                         "fecha": c.fecha.isoformat(), "hora": c.hora})
    return {"id": cita_id}


@router.put("/citas/{cita_id}/anular")
def anular_cita(cita_id: int, request: Request, centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("citas.editar")), session: Session = Depends(get_session)) -> dict:
    c = session.get(Cita, cita_id)
    if not c or c.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")
    anulada_id = estado_id_por_codigo(session, centro_id, "anulada", c.agenda_id)
    if anulada_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El centro no tiene un estado 'anulada' en su catálogo")
    estado_anterior = c.estado_id
    c.estado_id = anulada_id
    _marcar_modificacion(c, True)
    session.add(c); session.commit()
    _audit(session, user, centro_id, "agenda.cita.anular", f"cita:{cita_id}", request,
           {"estado_anterior": estado_anterior, "estado_id": anulada_id})
    emit("cita.anulada", {"cita_id": cita_id, "centro_id": centro_id, "paciente_id": c.paciente_id})
    return {"id": cita_id}


class EstadoCitaIn(BaseModel):
    estado_id: int


@router.put("/citas/{cita_id}/estado")
def cambiar_estado_cita(cita_id: int, data: EstadoCitaIn, request: Request, centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission("citas.editar")), session: Session = Depends(get_session)) -> dict:
    """Cambio rápido de estado desde la agenda (menú contextual). El estado debe existir en el
    catálogo estados_cita del centro; así el atajo no puede meter un estado inventado."""
    c = session.get(Cita, cita_id)
    if not c or c.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")
    est = session.get(EstadoCita, data.estado_id)
    if not est or est.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estado de cita no encontrado")
    estado_anterior = c.estado_id
    c.estado_id = data.estado_id
    _marcar_modificacion(c, True)
    session.add(c); session.commit()
    _audit(session, user, centro_id, "agenda.cita.estado", f"cita:{cita_id}", request,
           {"estado_anterior": estado_anterior, "estado_id": data.estado_id})
    emit("cita.actualizada", {"cita_id": cita_id, "centro_id": centro_id, "paciente_id": c.paciente_id,
                              "estado_id": data.estado_id, "estado_codigo": est.codigo})
    return {"id": cita_id, "estado_id": data.estado_id}


# ─────────────────── Justificante de asistencia (PDF de servidor) ───────────────────
@router.get("/citas/{cita_id}/justificante")
def justificante_cita(cita_id: int,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission("pacientes.ver")),
                      session: Session = Depends(get_session)):
    """PDF de justificante de asistencia de una cita, para entregar/imprimir desde la agenda.
    Mismo render que el de la app del paciente (documento_paciente_pdf), de modo que el
    justificante sea idéntico se pida desde donde se pida."""
    cita = session.get(Cita, cita_id)
    if not cita or cita.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")
    if not cita.paciente_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La cita no tiene paciente asignado")
    pac = session.get(Paciente, cita.paciente_id)
    if not pac:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    if not cita.fecha:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La cita no tiene fecha")

    doctor = ""
    if cita.colaborador_id:
        row = session.exec(
            select(Usuario.nombre, Usuario.apellidos)
            .join(UsuarioPeriodo, UsuarioPeriodo.usuario_id == Usuario.id)
            .join(Colaborador, Colaborador.periodo_id == UsuarioPeriodo.id)
            .where(Colaborador.id == cita.colaborador_id)).first()
        if row:
            doctor = f"{row[0]} {row[1] or ''}".strip()

    concepto = ""
    if cita.tipo_cita_id:
        tc = session.get(TipoCita, cita.tipo_cita_id)
        concepto = tc.nombre if tc else ""

    centro = session.get(Centro, centro_id)
    razon = session.exec(select(RazonSocial).where(RazonSocial.centro_id == centro_id)).first()
    with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = Path(tmp.name)
    render_justificante_pdf(
        pdf_path,
        centro={"nombre": centro.nombre if centro else None,
                "direccion": centro.direccion if centro else None,
                "poblacion": centro.poblacion if centro else None,
                "cif": razon.cif if razon else None},
        paciente={"nombre": f"{pac.nombre or ''} {pac.apellidos or ''}".strip(), "nif": pac.nif},
        fecha=cita.fecha, concepto=concepto, doctor=doctor,
    )
    return FileResponse(str(pdf_path), media_type="application/pdf",
                        filename=f"justificante_{cita_id}.pdf",
                        background=BackgroundTask(os.unlink, str(pdf_path)))
