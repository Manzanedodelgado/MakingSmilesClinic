"""Configuración · ROLES y sus PERMISOS (Config › Clínica › Centro).

Un rol = nombre + conjunto de permisos del catálogo gestionable. El rol marca el TECHO de lo
que puede hacer una persona; en Config › Personal se pueden quitar permisos concretos a una
persona concreta (user_center_permisos_denegados) pero nunca ampliar por encima del rol.
Efectivos de una persona = (permisos del rol − límites) ∪ concesiones directas heredadas.
Toda escritura se audita.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, func
from sqlmodel import Session, select

from api.audit_helper import _audit
from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.configuracion_staff_router import _areas_estructuradas, _catalogo_permisos
from application.services.auth_service import PERMISO_NO_GESTIONABLE
from domain.models.identidad import Permiso, Rol, RolePermiso, UserCenterPermisoDenegado, UserCenterRole
from infrastructure.config.db import get_session

router = APIRouter(prefix="/configuracion/roles", tags=["configuración · roles y permisos"])

# El rol de administración no se puede borrar ni renombrar, y siempre conserva el acceso a
# Configuración: sin él nadie podría volver a editar roles (bloqueo del centro).
ROL_SISTEMA = "Administrador"
PERMISOS_OBLIGATORIOS_SISTEMA = {"config.ver", "config.editar"}


class RolIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    permisos: list[str] = []


def _codigos_rol(session: Session, rol_id: int) -> list[str]:
    return sorted(c for c in session.exec(
        select(Permiso.codigo).join(RolePermiso, RolePermiso.permiso_id == Permiso.id)
        .where(RolePermiso.rol_id == rol_id)).all() if c not in PERMISO_NO_GESTIONABLE)


def _dto(session: Session, r: Rol) -> dict:
    n = session.exec(select(func.count()).select_from(UserCenterRole).where(UserCenterRole.rol_id == r.id)).one()
    return {"id": r.id, "nombre": r.nombre, "descripcion": r.descripcion,
            "permisos": _codigos_rol(session, r.id), "usuarios": int(n), "sistema": r.nombre == ROL_SISTEMA}


def _rol_del_centro(session: Session, rol_id: int, centro_id: int) -> Rol:
    r = session.get(Rol, rol_id)
    if not r or r.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rol no encontrado")
    return r


def _validar(session: Session, data: RolIn, centro_id: int, rol_id: Optional[int], es_sistema: bool) -> dict[str, int]:
    nombre = data.nombre.strip()
    if not nombre:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El nombre del rol es obligatorio")
    dup = session.exec(select(Rol).where(Rol.centro_id == centro_id, func.lower(Rol.nombre) == nombre.lower())).all()
    if any(d.id != rol_id for d in dup):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe un rol llamado «{nombre}»")
    catalogo = {p.codigo: p.id for p in _catalogo_permisos(session)}
    desconocidos = [c for c in data.permisos if c not in catalogo]
    if desconocidos:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Permisos no válidos: " + ", ".join(sorted(desconocidos)))
    if es_sistema:
        if nombre != ROL_SISTEMA:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El rol «{ROL_SISTEMA}» no se puede renombrar")
        falta = PERMISOS_OBLIGATORIOS_SISTEMA - set(data.permisos)
        if falta:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"«{ROL_SISTEMA}» debe conservar: " + ", ".join(sorted(falta)))
    return {c: catalogo[c] for c in set(data.permisos)}


@router.get("")
def listar_roles(centro_id: int = Depends(get_current_centro),
                 _u: CurrentUser = Depends(require_permission("config.ver")),
                 session: Session = Depends(get_session)) -> dict:
    roles = session.exec(select(Rol).where(Rol.centro_id == centro_id).order_by(Rol.nombre)).all()
    areas, extras = _areas_estructuradas(session)
    return {"roles": [_dto(session, r) for r in roles], "permiso_areas": areas, "permiso_extras": extras}


@router.post("", status_code=201)
def crear_rol(data: RolIn, request: Request, centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission("config.editar")),
              session: Session = Depends(get_session)) -> dict:
    ids = _validar(session, data, centro_id, None, False)
    r = Rol(centro_id=centro_id, nombre=data.nombre.strip(), descripcion=data.descripcion)
    session.add(r); session.flush()
    for pid in ids.values():
        session.add(RolePermiso(rol_id=r.id, permiso_id=pid))
    session.commit(); session.refresh(r)
    _audit(session, user, centro_id, "config.rol.crear", f"rol:{r.id}", request, {"permisos": sorted(ids)})
    return _dto(session, r)


@router.put("/{rol_id}")
def editar_rol(rol_id: int, data: RolIn, request: Request, centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("config.editar")),
               session: Session = Depends(get_session)) -> dict:
    r = _rol_del_centro(session, rol_id, centro_id)
    antes = _codigos_rol(session, r.id)
    ids = _validar(session, data, centro_id, r.id, r.nombre == ROL_SISTEMA)
    r.nombre = data.nombre.strip(); r.descripcion = data.descripcion
    session.add(r)
    session.exec(sa_delete(RolePermiso).where(RolePermiso.rol_id == r.id))
    for pid in ids.values():
        session.add(RolePermiso(rol_id=r.id, permiso_id=pid))
    # Los límites guardados de permisos que el rol ya no da dejan de tener sentido.
    cat = {p.codigo: p.id for p in _catalogo_permisos(session)}
    quitados = [cat[c] for c in antes if c in cat and c not in ids]
    if quitados:
        usuarios = list(session.exec(select(UserCenterRole.usuario_id).where(UserCenterRole.rol_id == r.id)).all())
        if usuarios:
            session.exec(sa_delete(UserCenterPermisoDenegado).where(
                UserCenterPermisoDenegado.centro_id == centro_id,
                UserCenterPermisoDenegado.usuario_id.in_(usuarios),
                UserCenterPermisoDenegado.permiso_id.in_(quitados)))
    session.commit(); session.refresh(r)
    _audit(session, user, centro_id, "config.rol.editar", f"rol:{r.id}", request,
           {"antes": antes, "despues": sorted(ids)})
    return _dto(session, r)


@router.delete("/{rol_id}", status_code=204)
def borrar_rol(rol_id: int, request: Request, centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("config.editar")),
               session: Session = Depends(get_session)) -> None:
    r = _rol_del_centro(session, rol_id, centro_id)
    if r.nombre == ROL_SISTEMA:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El rol «{ROL_SISTEMA}» no se puede borrar")
    n = session.exec(select(func.count()).select_from(UserCenterRole).where(UserCenterRole.rol_id == r.id)).one()
    if n:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Hay {n} persona(s) con este rol. Reasígnalas antes de borrarlo.")
    session.exec(sa_delete(RolePermiso).where(RolePermiso.rol_id == r.id))
    session.delete(r)
    session.commit()
    _audit(session, user, centro_id, "config.rol.borrar", f"rol:{rol_id}", request, {"nombre": r.nombre})
