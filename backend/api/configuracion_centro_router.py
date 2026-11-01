"""Configuración · CENTRO — agrega todo lo del centro SIN duplicar tablas.

identidad → centros · facturación → razones_sociales · configurable → configuraciones
(cerebro) · credenciales → integraciones · catálogos → estados_cita, gabinetes.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, get_current_user, require_permission
from api.audit_helper import _audit
from application.services.auth_service import AuthService
from application.services.config_service import ConfigService
from domain.models.agenda import EstadoCita, Gabinete
from domain.models.config import Integracion
from domain.models.core import Centro, RazonSocial
from infrastructure.config.db import get_session

router = APIRouter(prefix="/configuracion/centro", tags=["configuración · centro"])
SISTEMA = "cuidarte"
# Código del centro, razón social y CIF solo se editan desde Superusuario (API interna).
CENTRO_EDITABLE = {"nombre", "direccion", "cp", "poblacion", "provincia", "telefono",
                   "telefono_movil", "email", "web", "instagram", "logo_url", "icono_url", "num_gabinetes"}
RAZON_EDITABLE = {"licencia_sanitaria", "direccion", "cp", "poblacion", "provincia",
                  "serie", "iban", "sello_url"}
CONFIG_KEYS = {"centro.horario": None, "centro.festivos": None, "marca.colores": None,
               "gestoria.asesoria": None, "agenda.intervalo_min": SISTEMA, "agenda.vista_defecto": SISTEMA,
               "agenda.params": None}  # {intervalo, vistaDefecto} — parámetros de agenda


class CentroIn(BaseModel):
    nombre: Optional[str] = None; codigo: Optional[str] = None; direccion: Optional[str] = None
    cp: Optional[str] = None; poblacion: Optional[str] = None; provincia: Optional[str] = None
    telefono: Optional[str] = None; telefono_movil: Optional[str] = None; email: Optional[str] = None
    web: Optional[str] = None; instagram: Optional[str] = None; num_gabinetes: Optional[int] = None
    logo_url: Optional[str] = None; icono_url: Optional[str] = None


class RazonIn(BaseModel):
    nombre: str; cif: Optional[str] = None; licencia_sanitaria: Optional[str] = None
    direccion: Optional[str] = None; cp: Optional[str] = None; poblacion: Optional[str] = None
    provincia: Optional[str] = None; serie: Optional[str] = None; iban: Optional[str] = None
    sello_url: Optional[str] = None


class ConfigIn(BaseModel):
    clave: str; valor: Any = None


class IntegracionIn(BaseModel):
    tipo: str; nombre: Optional[str] = None; config: Any = None
    agente: Optional[str] = None   # solo relevante para tipo='llm' (alex|consulta_viva|gestoria_gastos|gestoria_facturas)
    activo: Optional[bool] = None  # None = no tocar (compat); permite desactivar un override de modelo por agente


class EstadoIn(BaseModel):
    codigo: str; nombre: str; color: Optional[str] = None; orden: Optional[int] = None; activo: bool = True


class GabineteIn(BaseModel):
    nombre: str; activo: bool = True


# ── Secretos de integración: NUNCA se devuelven al cliente en claro (se enmascaran). ──
# Al guardar, si llega la máscara sin cambiar, se conserva el valor existente (no se borra).
# Se detectan por NOMBRE de clave (robusto ante cualquier tipo de integración, presente o futuro).
_MASK = "••••••"
_MARCAS_SECRETO = ("password", "passwd", "secret", "token", "api_key", "apikey",
                   "hmac", "private", "sa_b64", "credential", "_key")


def _es_secreto(clave: str) -> bool:
    c = (clave or "").lower()
    return any(m in c for m in _MARCAS_SECRETO)


def _enmascarar_valor(v):
    if isinstance(v, dict):
        return {k: (_MASK if (x and _es_secreto(k) and not isinstance(x, (dict, list)))
                    else _enmascarar_valor(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_enmascarar_valor(x) for x in v]
    return v


def _enmascarar(tipo: str, config) -> dict:
    """Copia del config con TODO campo cuyo nombre delata un secreto sustituido por la máscara,
    a CUALQUIER profundidad. Antes solo miraba el primer nivel y `ocr.api_key`, las claves de
    `relevos` y el `oauth_borrado` de Drive salían en claro a cualquier usuario (23-oct-2026)."""
    return _enmascarar_valor(dict(config or {}))


def _clave_lista(x) -> Optional[str]:
    """Identidad de un elemento de lista (p. ej. un relevo) para casarlo aunque se reordene."""
    if isinstance(x, dict):
        for k in ("nombre", "id", "base_url"):
            if x.get(k):
                return f"{k}:{x[k]}"
    return None


def _fusionar_valor(nuevo, prev):
    if isinstance(nuevo, dict) and isinstance(prev, dict):
        out = {}
        for k, v in nuevo.items():
            if _es_secreto(k) and not isinstance(v, (dict, list)) and v in (_MASK, "", None) and prev.get(k):
                out[k] = prev[k]
            else:
                out[k] = _fusionar_valor(v, prev.get(k))
        return out
    if isinstance(nuevo, list) and isinstance(prev, list):
        por_clave = {_clave_lista(p): p for p in prev if _clave_lista(p)}
        return [_fusionar_valor(x, por_clave.get(_clave_lista(x)) if _clave_lista(x)
                                else (prev[i] if i < len(prev) else None))
                for i, x in enumerate(nuevo)]
    return nuevo


def _fusionar_secretos(tipo: str, nuevo, existente) -> dict:
    """Al guardar: si un secreto llega como máscara (o vacío), conserva el valor previo (no lo
    borra), a cualquier profundidad; en listas se casa por nombre/id aunque se reordenen."""
    return _fusionar_valor(dict(nuevo or {}), dict(existente or {}))


@router.get("")
def get_centro(centro_id: int = Depends(get_current_centro), _u: CurrentUser = Depends(get_current_user),
              session: Session = Depends(get_session)) -> dict:
    centro = session.get(Centro, centro_id)
    if not centro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centro no encontrado")
    # Si este centro comparte razón social con otro (asociación SuperUser), no tiene una
    # propia: se resuelve la del centro asociado, nunca se busca por su propio centro_id.
    if centro.razon_social_compartida_id:
        razon = session.get(RazonSocial, centro.razon_social_compartida_id)
    else:
        razon = session.exec(select(RazonSocial).where(RazonSocial.centro_id == centro_id, RazonSocial.activa == True)).first()  # noqa: E712
    estados = session.exec(select(EstadoCita).where(EstadoCita.centro_id == centro_id).order_by(EstadoCita.orden)).all()
    gabinetes = session.exec(select(Gabinete).where(Gabinete.centro_id == centro_id).order_by(Gabinete.id)).all()
    integraciones = session.exec(select(Integracion).where(Integracion.centro_id == centro_id)).all()
    cfg = ConfigService(session).for_scope(centro_id=centro_id, sistema=SISTEMA)
    # Los secretos de cada integración se ENMASCARAN antes de salir al cliente (no viajan en claro).
    integr_dto = [{"id": ig.id, "tipo": ig.tipo, "nombre": ig.nombre, "activo": ig.activo,
                   "agente": ig.agente, "config": _enmascarar(ig.tipo, ig.config)} for ig in integraciones]
    return {"centro": centro, "razon_social": razon, "config": {k: cfg.get(k) for k in CONFIG_KEYS},
            "integraciones": integr_dto, "estados_cita": estados, "gabinetes": gabinetes}


@router.put("/datos")
def update_datos(data: CentroIn, request: Request, centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> Centro:
    centro = session.get(Centro, centro_id)
    if not centro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centro no encontrado")
    cambios = data.model_dump(exclude_unset=True)
    for k, v in cambios.items():
        if k in CENTRO_EDITABLE:
            setattr(centro, k, v)
    session.add(centro); session.commit()
    _audit(session, user, centro_id, "config.centro.editar", "centro", request, cambios)
    return session.get(Centro, centro_id)


@router.put("/razon-social/{razon_id}")
def update_razon(razon_id: int, data: RazonIn, request: Request, centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> RazonSocial:
    razon = session.get(RazonSocial, razon_id)
    if not razon or razon.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Razón social no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        if k in RAZON_EDITABLE:
            setattr(razon, k, v)
    session.add(razon); session.commit()
    _audit(session, user, centro_id, "config.razon.editar", f"razon_social:{razon_id}", request)
    return session.get(RazonSocial, razon_id)


@router.put("/config")
def set_config(data: ConfigIn, request: Request, centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    if data.clave not in CONFIG_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Clave no editable: {data.clave}")
    row = ConfigService(session).set(data.clave, data.valor, centro_id=centro_id, sistema=CONFIG_KEYS[data.clave])
    _audit(session, user, centro_id, "config.cerebro.editar", f"config:{data.clave}", request)
    return {"clave": row.clave, "valor": row.valor}


@router.put("/integracion")
def set_integracion(data: IntegracionIn, request: Request, centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> dict:
    row = session.exec(select(Integracion).where(
        Integracion.centro_id == centro_id, Integracion.tipo == data.tipo,
        Integracion.agente == data.agente)).first()
    # Merge de secretos: si el cliente reenvía la máscara (no cambió el secreto), conserva el previo.
    cfg = _fusionar_secretos(data.tipo, data.config, row.config if row else {})
    # Google muestra las app passwords como 'xxxx xxxx xxxx xxxx'; pegada con espacios, Gmail
    # devuelve 535 BadCredentials. Se normaliza al guardar (solo email; otros secretos intactos).
    if data.tipo in ("email_saliente", "email_imap") and cfg.get("password"):
        cfg["password"] = cfg["password"].replace(" ", "")
    if row:
        row.nombre = data.nombre; row.config = cfg
        if data.activo is not None:
            row.activo = data.activo
    else:
        row = Integracion(centro_id=centro_id, tipo=data.tipo, nombre=data.nombre, config=cfg,
                          agente=data.agente, activo=data.activo if data.activo is not None else True)
    session.add(row); session.commit(); session.refresh(row)
    _audit(session, user, centro_id, "config.integracion.editar", f"integracion:{data.tipo}", request)
    # Respuesta con secretos enmascarados (nunca en claro al cliente).
    return {"id": row.id, "tipo": row.tipo, "nombre": row.nombre, "activo": row.activo,
            "agente": row.agente, "config": _enmascarar(row.tipo, row.config)}


@router.get("/ollama-switch")
def ollama_switch_estado(centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission("config.editar")),
                         session: Session = Depends(get_session)) -> dict:
    """Estado del motor local de Alex/Víctor/Aura (Ollama en el PC con GPU). Interruptor
    manual — nunca automático, porque ese PC comparte GPU con el escáner Medit i500."""
    from application.services import ollama_switch_service
    return ollama_switch_service.estado(session, centro_id)


@router.post("/ollama-switch/{accion}")
def ollama_switch_toggle(accion: str, request: Request, centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission("config.editar")),
                         session: Session = Depends(get_session)) -> dict:
    if accion not in ("encender", "apagar"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Acción no válida")
    from application.services import ollama_switch_service
    try:
        if accion == "encender":
            res = ollama_switch_service.encender(session, centro_id)
        else:
            res = ollama_switch_service.apagar(session, centro_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    _audit(session, user, centro_id, f"config.ollama_switch.{accion}", "ollama_switch", request, res)
    return res


@router.get("/ollama-switch/agentes")
def ollama_switch_agentes_estado(centro_id: int = Depends(get_current_centro),
                                 user: CurrentUser = Depends(require_permission("config.editar")),
                                 session: Session = Depends(get_session)) -> dict:
    """Estado de los 3 interruptores específicos (Alex/Víctor/Aura). El general (arriba)
    manda siempre: si el motor está apagado, ninguno responde aunque su específico diga
    activo=true."""
    from application.services import ollama_switch_service
    return ollama_switch_service.estado_agentes(session, centro_id)


@router.post("/ollama-switch/agentes/{agente}/{accion}")
def ollama_switch_agente_toggle(agente: str, accion: str, request: Request,
                                centro_id: int = Depends(get_current_centro),
                                user: CurrentUser = Depends(require_permission("config.editar")),
                                session: Session = Depends(get_session)) -> dict:
    from application.services import ollama_switch_service
    if agente not in ollama_switch_service.AGENTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Agente no válido")
    if accion not in ("encender", "apagar"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Acción no válida")
    try:
        res = ollama_switch_service.toggle_agente(session, centro_id, agente, accion == "encender")
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    _audit(session, user, centro_id, f"config.ollama_switch_agente.{accion}", f"ollama_switch:{agente}", request, res)
    return res


@router.put("/estado/{estado_id}")
def update_estado(estado_id: int, data: EstadoIn, request: Request, centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> EstadoCita:
    e = session.get(EstadoCita, estado_id)
    if not e or e.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estado no encontrado")
    e.codigo, e.nombre, e.color, e.orden, e.activo = data.codigo, data.nombre, data.color, data.orden, data.activo
    session.add(e); session.commit()
    _audit(session, user, centro_id, "config.estado.editar", f"estado_cita:{estado_id}", request)
    return session.get(EstadoCita, estado_id)


@router.post("/gabinete", status_code=201)
def add_gabinete(data: GabineteIn, request: Request, centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> Gabinete:
    if not data.nombre.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El gabinete necesita un nombre")
    g = Gabinete(centro_id=centro_id, nombre=data.nombre.strip(), activo=data.activo)
    session.add(g); session.commit(); session.refresh(g)
    gid = g.id
    _audit(session, user, centro_id, "config.gabinete.crear", f"gabinete:{gid}", request)
    return session.get(Gabinete, gid)


@router.delete("/gabinete/{gabinete_id}", status_code=204)
def del_gabinete(gabinete_id: int, request: Request, centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("config.editar")), session: Session = Depends(get_session)) -> None:
    g = session.get(Gabinete, gabinete_id)
    if not g or g.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gabinete no encontrado")
    session.delete(g); session.commit()
    _audit(session, user, centro_id, "config.gabinete.borrar", f"gabinete:{gabinete_id}", request)
