"""API INTERNA de administración de tenant — el ÚNICO punto por el que se toca la BBDD
operativa de un centro (pacientes/citas/personal/razón social/asociación) desde fuera del
propio centro. SuperUser (BBDD de plataforma, separada) llama aquí en vez de hacer joins
directos: así su base de datos "no tiene nada que ver" con la operativa.

Protegido por clave compartida (`X-Internal-Key` == settings.internal_api_key), NO por el
JWT de usuario — quien llama es el propio backend (SuperUser), no un navegador."""
import hmac
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import delete as sa_delete, func
from sqlmodel import Session, select

from application.services.auth_service import PERMISO_NO_GESTIONABLE, AuthService
from application.services.provision_service import ProvisionError, ProvisionService, compartir_personal_existente
from domain.config.settings import settings
from domain.models.config import Integracion
from domain.models.core import Centro, CentroAsociacion, Cita, Paciente, RazonSocial
from domain.models.identidad import Permiso, Rol, Usuario, UserCenterPermiso, UserCenterRole
from infrastructure.config.db import get_session
from infrastructure.security import hash_password

router = APIRouter(prefix="/internal/tenant", tags=["internal · tenant"])


def _internal_auth(x_internal_key: Optional[str] = Header(default=None)) -> None:
    if not x_internal_key or not hmac.compare_digest(x_internal_key, settings.internal_api_key or ""):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clave interna inválida")


def _audit_relay(session: Session, request: Request, actor_usuario_id: Optional[int],
                 centro_id: int, accion: str, recurso: str, detalle: Optional[dict] = None) -> None:
    """Auditoría de una acción relayada desde SuperUser: el actor real viaja en el body
    (`actor_usuario_id`), no en un JWT — esta llamada es interna, no de usuario."""
    if not actor_usuario_id:
        return
    AuthService(session).audit(accion, usuario_id=actor_usuario_id, centro_id=centro_id, recurso=recurso,
                               detalle=detalle, ip=request.client.host if request.client else None)


_CAMPOS_EDITABLES = ("nombre", "codigo", "direccion", "cp", "poblacion", "provincia", "telefono",
                    "telefono_movil", "email", "web", "instagram", "num_gabinetes")


@router.post("/provisionar", status_code=201, dependencies=[Depends(_internal_auth)])
def provisionar(body: dict, session: Session = Depends(get_session)) -> dict:
    """Crea un centro OPERATIVO completo (razón social, agenda+catálogos, rol admin, primer
    usuario). El registro de plataforma (nombre/estado/plan) lo guarda quien llama."""
    body = body or {}
    try:
        res = ProvisionService(session).provisionar_centro(
            nombre=body.get("nombre", ""),
            admin_nombre=body.get("admin_nombre", ""),
            admin_email=body.get("admin_email", ""),
            actor_usuario_id=body.get("actor_usuario_id"),
            asociado_a_centro_id=body.get("asociado_a_centro_id"),
            comparte_personal=bool(body.get("comparte_personal")),
            comparte_razon_social=bool(body.get("comparte_razon_social")),
            comparte_pacientes=bool(body.get("comparte_pacientes")),
        )
    except ProvisionError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return res


@router.get("/{centro_id}/detalle", dependencies=[Depends(_internal_auth)])
def detalle(centro_id: int, session: Session = Depends(get_session)) -> dict:
    centro = session.get(Centro, centro_id)
    if not centro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centro no encontrado")

    if centro.razon_social_compartida_id:
        rs = session.get(RazonSocial, centro.razon_social_compartida_id)
        razon_social = {**rs.model_dump(mode="json"), "compartida_de_centro_id": rs.centro_id} if rs else None
    else:
        rs = session.exec(select(RazonSocial).where(
            RazonSocial.centro_id == centro_id, RazonSocial.activa == True)).first()  # noqa: E712
        razon_social = rs.model_dump(mode="json") if rs else None

    asoc = session.exec(select(CentroAsociacion).where(CentroAsociacion.centro_id == centro_id)).first()
    asociacion = None
    if asoc:
        otro = session.get(Centro, asoc.asociado_a_centro_id)
        asociacion = {"asociado_a_centro_id": asoc.asociado_a_centro_id,
                     "asociado_a_nombre": otro.nombre if otro else None,
                     "comparte_personal": asoc.comparte_personal,
                     "comparte_razon_social": asoc.comparte_razon_social,
                     "comparte_pacientes": asoc.comparte_pacientes}

    accesos = session.exec(
        select(UserCenterRole, Usuario, Rol)
        .join(Usuario, Usuario.id == UserCenterRole.usuario_id)
        .join(Rol, Rol.id == UserCenterRole.rol_id)
        .where(UserCenterRole.centro_id == centro_id)
    ).all()
    personal = [{"usuario_id": u.id, "nombre": u.nombre, "email": u.email, "rol": r.nombre} for _, u, r in accesos]

    integraciones = session.exec(select(Integracion).where(Integracion.centro_id == centro_id)).all()
    n_pacientes = session.exec(select(func.count()).select_from(Paciente).where(Paciente.centro_id == centro_id)).one()
    n_citas = session.exec(select(func.count()).select_from(Cita).where(Cita.centro_id == centro_id)).one()
    ultima_cita = session.exec(select(Cita.fecha).where(Cita.centro_id == centro_id)
                              .order_by(Cita.fecha.desc())).first()

    alertas = []
    if not razon_social:
        alertas.append({"tipo": "error", "titulo": "Sin razón social",
                        "descripcion": "El centro no puede facturar sin una razón social activa."})
    if len(personal) == 0:
        alertas.append({"tipo": "error", "titulo": "Sin nadie con acceso",
                        "descripcion": "Ninguna persona tiene acceso a este centro."})
    elif len(personal) == 1:
        alertas.append({"tipo": "warning", "titulo": "Un solo acceso",
                        "descripcion": "Si esa persona pierde el acceso, nadie más puede entrar."})
    integraciones_inactivas = [i.tipo for i in integraciones if not i.activo]
    if integraciones_inactivas:
        alertas.append({"tipo": "warning", "titulo": "Integraciones configuradas pero inactivas",
                        "descripcion": ", ".join(integraciones_inactivas)})
    dias_desde_alta = (datetime.now() - centro.created_at.replace(tzinfo=None)).days if centro.created_at else 0
    if dias_desde_alta > 7 and int(n_pacientes) == 0:
        alertas.append({"tipo": "warning", "titulo": "Sin pacientes",
                        "descripcion": f"Creado hace {dias_desde_alta} días y sigue sin ningún paciente."})
    nivel_servicio = "critical" if any(a["tipo"] == "error" for a in alertas) else \
                      "degraded" if alertas else "ok"

    return {
        "centro": centro.model_dump(mode="json"),
        "razon_social": razon_social,
        "asociacion": asociacion,
        "personal": personal,
        "salud": {
            "nivel_servicio": nivel_servicio,
            "alertas": alertas,
            "integraciones": [{"tipo": i.tipo, "nombre": i.nombre, "activo": i.activo} for i in integraciones],
            "pacientes": int(n_pacientes), "citas": int(n_citas),
            "ultima_cita": ultima_cita.isoformat() if ultima_cita else None,
        },
    }


@router.put("/{centro_id}", dependencies=[Depends(_internal_auth)])
def actualizar(centro_id: int, body: dict, request: Request, session: Session = Depends(get_session)) -> dict:
    centro = session.get(Centro, centro_id)
    if not centro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centro no encontrado")
    body = body or {}
    cambios = {k: body[k] for k in _CAMPOS_EDITABLES if k in body}
    for k, v in cambios.items():
        setattr(centro, k, v)
    session.add(centro)
    # Razón social y CIF: solo desde Superusuario y solo la propia (una compartida se edita en su centro).
    rs_in = body.get("razon_social")
    if isinstance(rs_in, dict) and any(k in rs_in for k in ("nombre", "cif")):
        if centro.razon_social_compartida_id:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Este centro usa la razón social de otro centro; edítala desde ese centro")
        rs = session.exec(select(RazonSocial).where(
            RazonSocial.centro_id == centro_id, RazonSocial.activa == True)).first()  # noqa: E712
        if not rs:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "El centro no tiene razón social propia")
        if "nombre" in rs_in:
            nombre = (rs_in.get("nombre") or "").strip()
            if not nombre:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La razón social no puede quedar vacía")
            rs.nombre = nombre
            cambios["razon_social.nombre"] = nombre
        if "cif" in rs_in:
            rs.cif = (rs_in.get("cif") or "").strip().upper() or None
            cambios["razon_social.cif"] = rs.cif
        session.add(rs)
    session.commit()
    _audit_relay(session, request, body.get("actor_usuario_id"), centro_id,
                "superuser.centro.editar", f"centro:{centro_id}", cambios)
    return {"id": centro_id}


@router.put("/{centro_id}/asociacion", dependencies=[Depends(_internal_auth)])
def asociacion_set(centro_id: int, body: dict, request: Request, session: Session = Depends(get_session)) -> dict:
    centro = session.get(Centro, centro_id)
    if not centro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centro no encontrado")
    body = body or {}
    asociado_a = body.get("asociado_a_centro_id")
    comparte_personal = bool(body.get("comparte_personal"))
    comparte_razon_social = bool(body.get("comparte_razon_social"))
    comparte_pacientes = bool(body.get("comparte_pacientes"))
    existente = session.exec(select(CentroAsociacion).where(CentroAsociacion.centro_id == centro_id)).first()

    if asociado_a is None:
        if existente:
            session.delete(existente)
        if centro.razon_social_compartida_id:
            centro.razon_social_compartida_id = None
            if not session.exec(select(RazonSocial).where(RazonSocial.centro_id == centro_id)).first():
                session.add(RazonSocial(centro_id=centro_id, nombre=centro.nombre))
            session.add(centro)
        session.commit()
        _audit_relay(session, request, body.get("actor_usuario_id"), centro_id,
                    "superuser.centro.asociacion.quitar", f"centro:{centro_id}")
        return {"id": centro_id, "asociacion": None}

    otro = session.get(Centro, asociado_a)
    if not otro or otro.id == centro_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Centro asociado no válido")

    if existente:
        existente.asociado_a_centro_id = asociado_a
        existente.comparte_personal = comparte_personal
        existente.comparte_razon_social = comparte_razon_social
        existente.comparte_pacientes = comparte_pacientes
        session.add(existente)
    else:
        session.add(CentroAsociacion(centro_id=centro_id, asociado_a_centro_id=asociado_a,
                                     comparte_personal=comparte_personal, comparte_razon_social=comparte_razon_social,
                                     comparte_pacientes=comparte_pacientes))

    if comparte_razon_social:
        rs = session.exec(select(RazonSocial).where(
            RazonSocial.centro_id == otro.id, RazonSocial.activa == True)).first()  # noqa: E712
        if not rs:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{otro.nombre} no tiene razón social activa que compartir")
        centro.razon_social_compartida_id = rs.id
        session.add(centro)
    elif centro.razon_social_compartida_id:
        centro.razon_social_compartida_id = None
        if not session.exec(select(RazonSocial).where(RazonSocial.centro_id == centro_id)).first():
            session.add(RazonSocial(centro_id=centro_id, nombre=centro.nombre))
        session.add(centro)
    session.commit()

    personal_compartido = 0
    if comparte_personal:
        personal_compartido = compartir_personal_existente(
            session, centro_id=centro_id, centro_asociado_id=otro.id, nombre_asociado=otro.nombre)

    _audit_relay(session, request, body.get("actor_usuario_id"), centro_id,
                "superuser.centro.asociacion.editar", f"centro:{centro_id}",
                {"asociado_a_centro_id": asociado_a, "comparte_personal": comparte_personal,
                 "comparte_razon_social": comparte_razon_social, "comparte_pacientes": comparte_pacientes,
                 "personal_compartido": personal_compartido})
    return {"id": centro_id, "personal_compartido": personal_compartido}


@router.post("/{centro_id}/personal", dependencies=[Depends(_internal_auth)])
def personal_add(centro_id: int, body: dict, request: Request, session: Session = Depends(get_session)) -> dict:
    centro = session.get(Centro, centro_id)
    if not centro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centro no encontrado")
    body = body or {}
    email = (body.get("email") or "").strip().lower()
    nombre = (body.get("nombre") or "").strip()
    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Falta el email")
    usuario = session.exec(select(Usuario).where(Usuario.email == email)).first()
    password_temporal = None
    if not usuario:
        if not nombre:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                f"No existe nadie con el email {email} — indica también el nombre para crear una persona nueva")
        password_temporal = secrets.token_urlsafe(9)
        usuario = Usuario(nombre=nombre, email=email, password_hash=hash_password(password_temporal))
        session.add(usuario)
        session.commit()
        session.refresh(usuario)
    else:
        ya = session.exec(select(UserCenterRole).where(
            UserCenterRole.usuario_id == usuario.id, UserCenterRole.centro_id == centro_id)).first()
        if ya:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esa persona ya tiene acceso a este centro")
    rol = session.exec(select(Rol).where(Rol.centro_id == centro_id).order_by(Rol.id)).first()
    if not rol:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este centro no tiene ningún rol creado")
    session.add(UserCenterRole(usuario_id=usuario.id, centro_id=centro_id, rol_id=rol.id))
    permisos = session.exec(select(Permiso).where(Permiso.codigo.notin_(PERMISO_NO_GESTIONABLE))).all()
    session.add_all([UserCenterPermiso(usuario_id=usuario.id, centro_id=centro_id, permiso_id=p.id) for p in permisos])
    session.commit()
    _audit_relay(session, request, body.get("actor_usuario_id"), centro_id,
                "superuser.centro.personal.anadir", f"centro:{centro_id}",
                {"email": email, "creado": password_temporal is not None})
    return {"usuario_id": usuario.id, "nombre": usuario.nombre, "email": usuario.email, "password_temporal": password_temporal}


@router.delete("/{centro_id}/personal/{usuario_id}", dependencies=[Depends(_internal_auth)])
def personal_quitar(centro_id: int, usuario_id: int, request: Request, actor_usuario_id: Optional[int] = None,
                    session: Session = Depends(get_session)) -> dict:
    acceso = session.exec(select(UserCenterRole).where(
        UserCenterRole.usuario_id == usuario_id, UserCenterRole.centro_id == centro_id)).first()
    if not acceso:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa persona no tiene acceso a este centro")
    otros = session.exec(select(UserCenterRole).where(
        UserCenterRole.centro_id == centro_id, UserCenterRole.usuario_id != usuario_id)).first()
    if not otros:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se puede quitar el último acceso del centro")
    session.exec(sa_delete(UserCenterPermiso).where(
        UserCenterPermiso.usuario_id == usuario_id, UserCenterPermiso.centro_id == centro_id))
    session.delete(acceso)
    session.commit()
    _audit_relay(session, request, actor_usuario_id, centro_id,
                "superuser.centro.personal.quitar", f"centro:{centro_id}", {"usuario_id": usuario_id})
    return {"ok": True}


@router.post("/{centro_id}/personal/{usuario_id}/reset-password", dependencies=[Depends(_internal_auth)])
def personal_reset_password(centro_id: int, usuario_id: int, body: dict, request: Request,
                            session: Session = Depends(get_session)) -> dict:
    acceso = session.exec(select(UserCenterRole).where(
        UserCenterRole.usuario_id == usuario_id, UserCenterRole.centro_id == centro_id)).first()
    if not acceso:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa persona no tiene acceso a este centro")
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    password_temporal = secrets.token_urlsafe(9)
    usuario.password_hash = hash_password(password_temporal)
    session.add(usuario)
    session.commit()
    _audit_relay(session, request, (body or {}).get("actor_usuario_id"), centro_id,
                "superuser.centro.personal.reset_password", f"usuario:{usuario_id}")
    return {"usuario_id": usuario_id, "email": usuario.email, "password_temporal": password_temporal}


@router.put("/{centro_id}/personal/{usuario_id}/email", dependencies=[Depends(_internal_auth)])
def personal_email(centro_id: int, usuario_id: int, body: dict, request: Request,
                   session: Session = Depends(get_session)) -> dict:
    acceso = session.exec(select(UserCenterRole).where(
        UserCenterRole.usuario_id == usuario_id, UserCenterRole.centro_id == centro_id)).first()
    if not acceso:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa persona no tiene acceso a este centro")
    usuario = session.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    nuevo_email = ((body or {}).get("email") or "").strip().lower()
    if not nuevo_email or "@" not in nuevo_email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email no válido")
    if nuevo_email != usuario.email:
        choque = session.exec(select(Usuario).where(Usuario.email == nuevo_email)).first()
        if choque:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya existe otra persona con ese email")
    email_anterior = usuario.email
    usuario.email = nuevo_email
    session.add(usuario)
    session.commit()
    _audit_relay(session, request, (body or {}).get("actor_usuario_id"), centro_id,
                "superuser.centro.personal.email", f"usuario:{usuario_id}",
                {"anterior": email_anterior, "nuevo": nuevo_email})
    return {"usuario_id": usuario_id, "email": nuevo_email}
