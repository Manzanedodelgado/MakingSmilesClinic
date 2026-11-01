"""Endpoints de autenticación (capa de interfaz)."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, get_current_user
from application.services.auth_service import AuthError, AuthService
from application.services.config_service import ConfigService
from domain.models.core import Centro, Colaborador
from domain.models.identidad import Rol, Usuario, UserCenterRole, UsuarioPeriodo
from infrastructure.config.db import get_session
from domain.config.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/apariencia")
def apariencia_publica(session: Session = Depends(get_session)) -> dict:
    """Favicon/logo/icono de plataforma — público, lo necesitan login/recuperar/restablecer."""
    return ConfigService(session).resolve("plataforma.apariencia", default={}) or {}


_APARIENCIA_CAMPOS = {"favicon": "favicon_url", "logo": "logo_url", "icono": "icono_url"}
_MEDIA_DIR = (Path(__file__).resolve().parent.parent / "media").resolve()


@router.get("/apariencia/imagen/{campo}")
def apariencia_imagen(campo: str, session: Session = Depends(get_session)):
    """Sirve la imagen de marca (favicon/logo/icono) SIN login — excepción acotada a
    estos 3 campos de configuración."""
    clave = _APARIENCIA_CAMPOS.get(campo)
    if not clave:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    valor = ConfigService(session).resolve("plataforma.apariencia", default={}) or {}
    url = valor.get(clave)
    if not url or not url.startswith("/media/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    destino = (_MEDIA_DIR / url.removeprefix("/media/")).resolve()
    if destino != _MEDIA_DIR and _MEDIA_DIR not in destino.parents:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    if not destino.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    return FileResponse(destino, headers={"Cache-Control": "public, max-age=300"})


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotRequest(BaseModel):
    email: str


class ResetRequest(BaseModel):
    token: str
    password: str


@router.post("/login")
def login(data: LoginRequest, request: Request, response: Response, session: Session = Depends(get_session)) -> dict:
    """Login de clientes bearer (incluye la app móvil del doctor)."""
    return _login(data, request, response, session, include_token=True)


@router.post("/login-cookie")
def login_cookie(data: LoginRequest, request: Request, response: Response, session: Session = Depends(get_session)) -> dict:
    """Login web: guarda el JWT en cookie HttpOnly y nunca lo devuelve en JSON."""
    return _login(data, request, response, session, include_token=False)


def _login(data: LoginRequest, request: Request, response: Response, session: Session, *, include_token: bool) -> dict:
    ip = request.client.host if request.client else None
    try:
        result = AuthService(session).login(data.email, data.password, ip=ip)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
    response.set_cookie(
        key="access_token", value=result["access_token"], httponly=True,
        secure=settings.cookie_secure,
        samesite="lax", max_age=60 * 60 * 12, path="/",
    )
    if include_token:
        return result
    return {key: value for key, value in result.items() if key != "access_token"}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie("access_token", path="/", secure=settings.cookie_secure, samesite="lax")
    return {"ok": True}


@router.post("/forgot")
def forgot(data: ForgotRequest, request: Request, session: Session = Depends(get_session)) -> dict:
    ip = request.client.host if request.client else None
    base = settings.public_frontend_url
    AuthService(session).solicitar_reset(data.email.strip(), base, ip=ip)
    return {"ok": True, "mensaje": "Si el email existe, te hemos enviado un enlace."}


@router.post("/reset")
def reset(data: ResetRequest, request: Request, session: Session = Depends(get_session)) -> dict:
    ip = request.client.host if request.client else None
    try:
        AuthService(session).reset_password(data.token, data.password, ip=ip)
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"ok": True}


@router.get("/me")
def me(
    user: CurrentUser = Depends(get_current_user),
    centro_id: int = Depends(get_current_centro),
    session: Session = Depends(get_session),
) -> dict:
    permisos = AuthService(session).permisos_de(user.usuario_id, centro_id)
    ucr = session.exec(
        select(UserCenterRole).where(
            UserCenterRole.usuario_id == user.usuario_id, UserCenterRole.centro_id == centro_id
        )
    ).first()
    rol_nombre = session.get(Rol, ucr.rol_id).nombre if ucr else None
    u = session.get(Usuario, user.usuario_id)
    apellidos = u.apellidos if u else None
    nombre_completo = " ".join(p for p in [user.nombre, apellidos] if p)
    centro = session.get(Centro, centro_id)
    colaborador_id = session.exec(
        select(Colaborador.id)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .where(UsuarioPeriodo.usuario_id == user.usuario_id)
        .order_by(UsuarioPeriodo.id.desc())
    ).first()
    return {
        "usuario_id": user.usuario_id,
        "colaborador_id": colaborador_id,
        "nombre": user.nombre,
        "apellidos": apellidos,
        "nombre_completo": nombre_completo,
        "rol_nombre": rol_nombre,
        "centro_activo": centro_id,
        "centro_nombre": centro.nombre if centro else None,
        "centro_icono_url": centro.icono_url if centro else None,
        "centro_logo_url": centro.logo_url if centro else None,
        "accesos": user.accesos,
        "permisos": sorted(permisos),
    }
