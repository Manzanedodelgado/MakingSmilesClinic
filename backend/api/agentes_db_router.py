"""API para Agentes IA configurables (DB nueva, Plan 3+)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from application.services.agente_permisos_service import grant as _grant_permiso
from application.services.canal_ajuste_service import ajuste_para as _ajuste_para, upsert_ajuste as _upsert_ajuste
from application.services.personalidad_service import get_personalidad as _get_personalidad, upsert_personalidad as _upsert_personalidad
from domain.models.agentes import Agente, AgenteCapacidad, AgentePermisoAdmin, CapacidadCatalogo
from infrastructure.config.db import get_session

router = APIRouter(prefix="/agentes/db", tags=["ia · agentes db"])


@router.get("")
def listar(centro_id: int = Depends(get_current_centro), user: CurrentUser = Depends(require_permission("config.ver")), session: Session = Depends(get_session)):
    filas = session.exec(select(Agente).where(Agente.centro_id == centro_id).order_by(Agente.id)).all()
    return {"agentes": [f.model_dump() for f in filas]}


@router.get("/capacidades/catalogo")
def catalogo_capacidades(user: CurrentUser = Depends(require_permission("config.ver")), session: Session = Depends(get_session)):
    filas = session.exec(select(CapacidadCatalogo).order_by(CapacidadCatalogo.clave)).all()
    return {"capacidades": [f.model_dump() for f in filas]}


@router.post("/migrar-base")
def migrar_agentes_base(centro_id: int = Depends(get_current_centro), user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)):
    """Idempotente: crea (si faltan) las filas en `agentes` para Alex/Victor/Aura/Gestor de
    este centro, leyendo su config real actual. No toca el sistema legacy que los sirve hoy."""
    from application.services.migrar_agentes_reales import migrar_los_cuatro_agentes_reales
    agentes = migrar_los_cuatro_agentes_reales(session, centro_id)
    # Los commits intermedios de la migración (una fila por capacidad) dejan estos objetos
    # expirados; se releen antes de serializar para no devolver dicts vacíos.
    return {"agentes": [session.get(Agente, a.id).model_dump() for a in agentes]}


class CrearIn(BaseModel):
    nombre: str
    audiencia: str  # paciente|staff|superuser|facturacion|sistema
    rol_sub: Optional[str] = None
    modo_activacion: str = "manual"
    modelo_llm: Optional[str] = None
    config_key: str = ""
    es_agente_base: bool = False


@router.post("", status_code=201)
def crear(data: CrearIn, centro_id: int = Depends(get_current_centro), user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)):
    ag = Agente(centro_id=centro_id, nombre=data.nombre, audiencia=data.audiencia, rol_sub=data.rol_sub, modo_activacion=data.modo_activacion, modelo_llm=data.modelo_llm, config_key=data.config_key or f"agente.{data.nombre.lower()}", es_agente_base=data.es_agente_base)
    session.add(ag); session.commit(); session.refresh(ag)
    return ag.model_dump()


@router.get("/{agente_id}")
def detalle(agente_id: int, centro_id: int = Depends(get_current_centro), user: CurrentUser = Depends(require_permission("config.ver")), session: Session = Depends(get_session)):
    ag = session.get(Agente, agente_id)
    if not ag or ag.centro_id != centro_id:
        raise HTTPException(404, "Agente no encontrado")
    caps = session.exec(select(CapacidadCatalogo).join(AgenteCapacidad, AgenteCapacidad.capacidad_id == CapacidadCatalogo.id).where(AgenteCapacidad.agente_id == agente_id)).all()
    activas = {c.clave for c in session.exec(select(CapacidadCatalogo).join(AgenteCapacidad, AgenteCapacidad.capacidad_id == CapacidadCatalogo.id).where(AgenteCapacidad.agente_id == agente_id, AgenteCapacidad.activa == True)).all()}
    return {"agente": ag.model_dump(), "capacidades": [c.model_dump() for c in caps], "activas": sorted(activas)}


class CapsIn(BaseModel):
    claves: list[str]


@router.post("/{agente_id}/capacidades")
def set_caps(agente_id: int, data: CapsIn, centro_id: int = Depends(get_current_centro), user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)):
    ag = session.get(Agente, agente_id)
    if not ag or ag.centro_id != centro_id:
        raise HTTPException(404, "Agente no encontrado")
    # validar claves existen
    todas = {c.clave: c for c in session.exec(select(CapacidadCatalogo)).all()}
    for k in data.claves:
        if k not in todas:
            raise HTTPException(422, f"Capacidad desconocida: {k}")
    # upsert puente
    existentes = {ac.capacidad_id: ac for ac in session.exec(select(AgenteCapacidad).where(AgenteCapacidad.agente_id == agente_id)).all()}
    for clave, cap in todas.items():
        ac = existentes.get(cap.id)
        debe_activa = clave in data.claves
        if ac:
            if ac.activa != debe_activa:
                ac.activa = debe_activa; session.add(ac)
        else:
            if debe_activa:
                session.add(AgenteCapacidad(agente_id=agente_id, capacidad_id=cap.id, activa=True))
            # si no debe_activa y no existe, no crear fila
    # desactivar las que estaban activas pero ya no están en lista
    for ac in existentes.values():
        cap = session.get(CapacidadCatalogo, ac.capacidad_id)
        if cap and cap.clave not in data.claves and ac.activa:
            ac.activa = False; session.add(ac)
    session.commit()
    return {"ok": True}


def _obtener_propio(session: Session, agente_id: int, centro_id: int) -> Agente:
    ag = session.get(Agente, agente_id)
    if not ag or ag.centro_id != centro_id:
        raise HTTPException(404, "Agente no encontrado")
    return ag


class ActivacionIn(BaseModel):
    activo: Optional[bool] = None
    modo_activacion: Optional[str] = None  # manual|programado|ambos
    programacion: Optional[dict] = None  # {"cron": "0 9 * * 1"} o {"interval_seg": 60}


@router.patch("/{agente_id}")
def actualizar_activacion(agente_id: int, data: ActivacionIn, centro_id: int = Depends(get_current_centro),
                           user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)):
    ag = _obtener_propio(session, agente_id, centro_id)
    if data.activo is not None:
        ag.activo = data.activo
    if data.modo_activacion is not None:
        if data.modo_activacion not in ("manual", "programado", "ambos"):
            raise HTTPException(422, "modo_activacion debe ser manual|programado|ambos")
        ag.modo_activacion = data.modo_activacion
    if data.programacion is not None:
        ag.programacion = data.programacion
    session.add(ag); session.commit(); session.refresh(ag)
    return ag.model_dump()


class PersonalidadIn(BaseModel):
    idioma: Optional[str] = None
    tono: Optional[str] = None
    cercania: Optional[int] = None
    proactividad: Optional[int] = None
    formalidad: Optional[int] = None
    bienvenida: Optional[str] = None
    despedida: Optional[str] = None
    acento: Optional[str] = None
    velocidad: Optional[str] = None
    regla_extra: Optional[str] = None


@router.get("/{agente_id}/personalidad/{capa}")
def leer_personalidad(agente_id: int, capa: str, centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("config.ver")), session: Session = Depends(get_session)):
    _obtener_propio(session, agente_id, centro_id)
    fila = _get_personalidad(session, agente_id, capa)
    return {"personalidad": fila.model_dump() if fila else None}


@router.post("/{agente_id}/personalidad/{capa}")
def guardar_personalidad(agente_id: int, capa: str, data: PersonalidadIn, centro_id: int = Depends(get_current_centro),
                          user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)):
    _obtener_propio(session, agente_id, centro_id)
    campos = {k: v for k, v in data.model_dump().items() if v is not None}
    fila = _upsert_personalidad(session, agente_id, capa, **campos)
    return fila.model_dump()


class PermisoIn(BaseModel):
    rol_o_usuario: str
    puede_ver: bool = True
    puede_editar: bool = False


@router.get("/{agente_id}/permisos")
def listar_permisos(agente_id: int, centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission("config.ver")), session: Session = Depends(get_session)):
    _obtener_propio(session, agente_id, centro_id)
    filas = session.exec(select(AgentePermisoAdmin).where(AgentePermisoAdmin.agente_id == agente_id)).all()
    return {"permisos": [f.model_dump() for f in filas]}


@router.post("/{agente_id}/permisos")
def guardar_permiso(agente_id: int, data: PermisoIn, centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)):
    _obtener_propio(session, agente_id, centro_id)
    fila = _grant_permiso(session, agente_id, data.rol_o_usuario, data.puede_ver, data.puede_editar)
    return fila.model_dump()


class CanalIn(BaseModel):
    longitud_max: Optional[int] = None
    usa_emojis: Optional[bool] = None
    ritmo: Optional[str] = None
    extras: Optional[dict] = None


@router.get("/{agente_id}/canal/{canal}")
def leer_canal(agente_id: int, canal: str, centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("config.ver")), session: Session = Depends(get_session)):
    _obtener_propio(session, agente_id, centro_id)
    fila = _ajuste_para(session, agente_id, canal)
    return {"ajuste": fila.model_dump() if fila else None}


@router.post("/{agente_id}/canal/{canal}")
def guardar_canal(agente_id: int, canal: str, data: CanalIn, centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)):
    _obtener_propio(session, agente_id, centro_id)
    campos = {k: v for k, v in data.model_dump().items() if v is not None}
    fila = _upsert_ajuste(session, agente_id, canal, **campos)
    return fila.model_dump()
