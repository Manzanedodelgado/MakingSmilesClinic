"""Configuración · Clínica · AGENDA — sobre las tablas reales del modelo de agenda.

agendas (calendarios), tipos_cita (motivos con color/duración), estados_cita (colores),
gabinetes (recursos físicos) y colaborador_horarios (franjas de trabajo por colaborador).
Todo se lee y escribe en sus tablas (cero JSON suelto). Escrituras auditadas.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, select

from api.auth_deps import CurrentUser, get_current_centro, get_current_user, require_permission
from api.audit_helper import _audit
from api.colaborador_helper import colaboradores_activos_rows
from application.services.auth_service import AuthService
from application.services.config_service import ConfigService
from datetime import date, datetime

from domain.models.agenda import Agenda, BloqueoAgenda, ColaboradorExcepcion, ColaboradorHorario, EstadoCita, Gabinete, TipoCita
from domain.models.core import Colaborador
from domain.models.identidad import Usuario, UsuarioPeriodo
from infrastructure.config.db import get_session

router = APIRouter(prefix="/configuracion/agenda", tags=["configuración · agenda"])


def _persist(session: Session, obj: SQLModel, user, centro_id, accion, request) -> dict:
    """Guarda y captura el JSON ANTES de auditar (el commit de auditoría expira el objeto)."""
    session.add(obj); session.commit(); session.refresh(obj)
    out = obj.model_dump(mode="json")
    _audit(session, user, centro_id, accion, f"{accion.split('.')[1]}:{out.get('id')}", request)
    return out


def _colaboradores(session: Session, centro_id: int) -> list[dict]:
    """Colaboradores ACTIVOS para el selector de horarios (ver colaborador_helper)."""
    rows = colaboradores_activos_rows(session, centro_id)
    return [{"id": c.id, "nombre": f"{u.nombre} {u.apellidos or ''}".strip(), "color": u.color,
             "num_colegiado": c.num_colegiado, "staff_tipo": up.staff_tipo, "activo": c.activo}
            for c, u, up in rows]


def _colaborador_del_centro(session: Session, colaborador_id: int, centro_id: int) -> bool:
    return session.exec(
        select(Colaborador.id)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .where(Colaborador.id == colaborador_id, UsuarioPeriodo.centro_id == centro_id)
    ).first() is not None


def _recurso_del_centro(session: Session, modelo, recurso_id: Optional[int], centro_id: int) -> bool:
    if recurso_id is None:
        return True
    return session.exec(
        select(modelo.id).where(modelo.id == recurso_id, modelo.centro_id == centro_id)
    ).first() is not None


def _validar_horario(session: Session, data: "HorarioIn", centro_id: int) -> None:
    if not _colaborador_del_centro(session, data.colaborador_id, centro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colaborador no encontrado")
    if not _recurso_del_centro(session, Agenda, data.agenda_id, centro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agenda no encontrada")
    if not _recurso_del_centro(session, Gabinete, data.gabinete_id, centro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gabinete no encontrado")


def _validar_agenda(session: Session, agenda_id: Optional[int], centro_id: int) -> None:
    if not _recurso_del_centro(session, Agenda, agenda_id, centro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agenda no encontrada")


# ─────────────────────────── GET agregado ───────────────────────────
@router.get("")
def get_agenda(centro_id: int = Depends(get_current_centro), _u: CurrentUser = Depends(get_current_user),
               session: Session = Depends(get_session)) -> dict:
    ag = session.exec(select(Agenda).where(Agenda.centro_id == centro_id).order_by(Agenda.orden, Agenda.nombre)).all()
    tipos = session.exec(select(TipoCita).where(TipoCita.centro_id == centro_id).order_by(TipoCita.nombre)).all()
    estados = session.exec(select(EstadoCita).where(EstadoCita.centro_id == centro_id).order_by(EstadoCita.orden)).all()
    gabs = session.exec(select(Gabinete).where(Gabinete.centro_id == centro_id).order_by(Gabinete.nombre)).all()
    horarios = session.exec(
        select(ColaboradorHorario)
        .join(Colaborador, Colaborador.id == ColaboradorHorario.colaborador_id)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .where(ColaboradorHorario.centro_id == centro_id, UsuarioPeriodo.centro_id == centro_id)
        .order_by(ColaboradorHorario.colaborador_id, ColaboradorHorario.dia_semana)
    ).all()
    colaboradores = _colaboradores(session, centro_id)
    ids_colab = [c["id"] for c in colaboradores]
    excepciones = session.exec(
        select(ColaboradorExcepcion).where(ColaboradorExcepcion.colaborador_id.in_(ids_colab))
        .order_by(ColaboradorExcepcion.fecha_inicio)
    ).all() if ids_colab else []
    bloqueos = session.exec(
        select(BloqueoAgenda).where(BloqueoAgenda.centro_id == centro_id).order_by(BloqueoAgenda.fecha_inicio)
    ).all()
    params = ConfigService(session).resolve("agenda.params", centro_id=centro_id, default={}) or {}
    return {
        "agendas": ag, "tipos_cita": tipos, "estados_cita": estados, "gabinetes": gabs,
        "colaboradores": colaboradores, "horarios": horarios,
        "excepciones": excepciones, "bloqueos": bloqueos, "params": params,
    }


# ─────────────────────────── AGENDAS ───────────────────────────
class AgendaIn(BaseModel):
    nombre: str
    color: Optional[str] = None
    intervalo_min: Optional[int] = None
    vista_defecto: Optional[str] = None
    orden: Optional[int] = None
    activo: bool = True


@router.post("/agendas", status_code=201)
def crear_agenda(data: AgendaIn, request: Request, centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    a = Agenda(centro_id=centro_id, **data.model_dump())
    return _persist(session, a, user, centro_id, "config.agenda.crear", request)


@router.put("/agendas/{agenda_id}")
def editar_agenda(agenda_id: int, data: AgendaIn, request: Request, centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    a = session.get(Agenda, agenda_id)
    if not a or a.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agenda no encontrada")
    for k, v in data.model_dump().items():
        setattr(a, k, v)
    return _persist(session, a, user, centro_id, "config.agenda.editar", request)


@router.delete("/agendas/{agenda_id}", status_code=204)
def borrar_agenda(agenda_id: int, request: Request, centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> None:
    a = session.get(Agenda, agenda_id)
    if a and a.centro_id == centro_id:
        session.delete(a); session.commit()
        _audit(session, user, centro_id, "config.agenda.borrar", f"agenda:{agenda_id}", request)


# ─────────────────────────── TIPOS DE CITA ───────────────────────────
class TipoCitaIn(BaseModel):
    nombre: str
    color: Optional[str] = None
    agenda_id: Optional[int] = None
    activo: bool = True


@router.post("/tipos", status_code=201)
def crear_tipo(data: TipoCitaIn, request: Request, centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    _validar_agenda(session, data.agenda_id, centro_id)
    t = TipoCita(centro_id=centro_id, **data.model_dump())
    return _persist(session, t, user, centro_id, "config.tipocita.crear", request)


@router.put("/tipos/{tipo_id}")
def editar_tipo(tipo_id: int, data: TipoCitaIn, request: Request, centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    _validar_agenda(session, data.agenda_id, centro_id)
    t = session.get(TipoCita, tipo_id)
    if not t or t.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tipo de cita no encontrado")
    for k, v in data.model_dump().items():
        setattr(t, k, v)
    return _persist(session, t, user, centro_id, "config.tipocita.editar", request)


@router.delete("/tipos/{tipo_id}", status_code=204)
def borrar_tipo(tipo_id: int, request: Request, centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> None:
    t = session.get(TipoCita, tipo_id)
    if t and t.centro_id == centro_id:
        session.delete(t); session.commit()
        _audit(session, user, centro_id, "config.tipocita.borrar", f"tipo_cita:{tipo_id}", request)


# ─────────────────────────── ESTADOS DE CITA ───────────────────────────
class EstadoIn(BaseModel):
    nombre: str
    color: Optional[str] = None
    agenda_id: Optional[int] = None
    orden: Optional[int] = None
    activo: bool = True


@router.post("/estados", status_code=201)
def crear_estado(data: EstadoIn, request: Request, centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    _validar_agenda(session, data.agenda_id, centro_id)
    orden = data.orden
    if orden is None:
        existentes = session.exec(select(EstadoCita).where(EstadoCita.centro_id == centro_id)).all()
        orden = max([x.orden or 0 for x in existentes], default=0) + 1
    codigo = (data.nombre or "estado").strip().lower().replace(" ", "_")[:40] or "estado"
    e = EstadoCita(centro_id=centro_id, agenda_id=data.agenda_id, codigo=codigo, nombre=data.nombre, color=data.color, orden=orden, activo=data.activo)
    return _persist(session, e, user, centro_id, "config.estadocita.crear", request)


@router.put("/estados/{estado_id}")
def editar_estado(estado_id: int, data: EstadoIn, request: Request, centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    _validar_agenda(session, data.agenda_id, centro_id)
    e = session.get(EstadoCita, estado_id)
    if not e or e.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estado no encontrado")
    e.nombre, e.color, e.orden, e.activo = data.nombre, data.color, data.orden, data.activo
    return _persist(session, e, user, centro_id, "config.estadocita.editar", request)


@router.delete("/estados/{estado_id}", status_code=204)
def borrar_estado(estado_id: int, request: Request, centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> None:
    e = session.get(EstadoCita, estado_id)
    if e and e.centro_id == centro_id:
        session.delete(e); session.commit()
        _audit(session, user, centro_id, "config.estadocita.borrar", f"estado_cita:{estado_id}", request)


# ─────────────────────────── GABINETES ───────────────────────────
class GabineteIn(BaseModel):
    nombre: str
    agenda_id: Optional[int] = None
    activo: bool = True


@router.post("/gabinetes", status_code=201)
def crear_gabinete(data: GabineteIn, request: Request, centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    _validar_agenda(session, data.agenda_id, centro_id)
    g = Gabinete(centro_id=centro_id, **data.model_dump())
    return _persist(session, g, user, centro_id, "config.gabinete.crear", request)


@router.put("/gabinetes/{gabinete_id}")
def editar_gabinete(gabinete_id: int, data: GabineteIn, request: Request, centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    _validar_agenda(session, data.agenda_id, centro_id)
    g = session.get(Gabinete, gabinete_id)
    if not g or g.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gabinete no encontrado")
    g.nombre, g.activo, g.agenda_id = data.nombre, data.activo, data.agenda_id
    return _persist(session, g, user, centro_id, "config.gabinete.editar", request)


@router.delete("/gabinetes/{gabinete_id}", status_code=204)
def borrar_gabinete(gabinete_id: int, request: Request, centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> None:
    g = session.get(Gabinete, gabinete_id)
    if g and g.centro_id == centro_id:
        session.delete(g); session.commit()
        _audit(session, user, centro_id, "config.gabinete.borrar", f"gabinete:{gabinete_id}", request)


# ─────────────────────────── HORARIOS DE COLABORADORES ───────────────────────────
class HorarioIn(BaseModel):
    colaborador_id: int
    agenda_id: Optional[int] = None
    gabinete_id: Optional[int] = None
    dia_semana: int                      # 0=lunes … 6=domingo
    hora_inicio: str
    hora_fin: str
    pausa_inicio: Optional[str] = None
    pausa_fin: Optional[str] = None
    activo: bool = True


@router.post("/horarios", status_code=201)
def crear_horario(data: HorarioIn, request: Request, centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    _validar_horario(session, data, centro_id)
    h = ColaboradorHorario(centro_id=centro_id, **data.model_dump())
    return _persist(session, h, user, centro_id, "config.horario.crear", request)


@router.put("/horarios/{horario_id}")
def editar_horario(horario_id: int, data: HorarioIn, request: Request, centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    _validar_horario(session, data, centro_id)
    h = session.get(ColaboradorHorario, horario_id)
    if not h or h.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Horario no encontrado")
    for k, v in data.model_dump().items():
        setattr(h, k, v)
    return _persist(session, h, user, centro_id, "config.horario.editar", request)


@router.delete("/horarios/{horario_id}", status_code=204)
def borrar_horario(horario_id: int, request: Request, centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> None:
    h = session.get(ColaboradorHorario, horario_id)
    if h and h.centro_id == centro_id:
        session.delete(h); session.commit()
        _audit(session, user, centro_id, "config.horario.borrar", f"colaborador_horario:{horario_id}", request)


# ─────────────────────────── EXCEPCIONES DE COLABORADOR ───────────────────────────
class ExcepcionIn(BaseModel):
    colaborador_id: int
    fecha_inicio: date
    fecha_fin: date
    tipo: Optional[str] = None
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    pausa_inicio: Optional[str] = None
    pausa_fin: Optional[str] = None


@router.post("/excepciones", status_code=201)
def crear_excepcion(data: ExcepcionIn, request: Request, centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    if not _colaborador_del_centro(session, data.colaborador_id, centro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colaborador no encontrado")
    e = ColaboradorExcepcion(**data.model_dump())
    return _persist(session, e, user, centro_id, "config.excepcion.crear", request)


@router.delete("/excepciones/{excepcion_id}", status_code=204)
def borrar_excepcion(excepcion_id: int, request: Request, centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> None:
    e = session.get(ColaboradorExcepcion, excepcion_id)
    if e and _colaborador_del_centro(session, e.colaborador_id, centro_id):
        session.delete(e); session.commit()
        _audit(session, user, centro_id, "config.excepcion.borrar", f"colaborador_excepcion:{excepcion_id}", request)


# ─────────────────────────── VACACIONES / BLOQUEOS DE AGENDA ───────────────────────────
class BloqueoIn(BaseModel):
    colaborador_id: Optional[int] = None
    gabinete_id: Optional[int] = None
    fecha_inicio: datetime
    fecha_fin: datetime
    motivo: Optional[str] = None


@router.post("/bloqueos", status_code=201)
def crear_bloqueo(data: BloqueoIn, request: Request, centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    if data.colaborador_id is not None and not _colaborador_del_centro(session, data.colaborador_id, centro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colaborador no encontrado")
    if not _recurso_del_centro(session, Gabinete, data.gabinete_id, centro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gabinete no encontrado")
    b = BloqueoAgenda(centro_id=centro_id, **data.model_dump())
    return _persist(session, b, user, centro_id, "config.bloqueo.crear", request)


@router.delete("/bloqueos/{bloqueo_id}", status_code=204)
def borrar_bloqueo(bloqueo_id: int, request: Request, centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> None:
    b = session.get(BloqueoAgenda, bloqueo_id)
    if b and b.centro_id == centro_id:
        session.delete(b); session.commit()
        _audit(session, user, centro_id, "config.bloqueo.borrar", f"bloqueo_agenda:{bloqueo_id}", request)
