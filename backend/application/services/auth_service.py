"""Autenticación, RBAC y auditoría.

Login de personal de centro → JWT que lleva los accesos (user × centro × rol).
El ACCESO se resuelve por `user_center_roles`, NUNCA por un campo role plano.
Los permisos finos se cargan por (usuario, centro) vía roles → role_permisos y
concesiones directas / denegadas.
"""
import hashlib
import json
import logging
import secrets
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlmodel import Session, select

from domain.models.auditoria import Auditoria
from domain.models.identidad import (
    PasswordReset, Permiso, Rol, RolePermiso, Usuario, UserCenterRole,
    UserCenterPermiso, UserCenterPermisoDenegado, UsuarioPeriodo,
)
from infrastructure.mailer import send_email
from infrastructure.security import create_access_token, hash_password, verify_password

logger = logging.getLogger("centinela.auth")

# `superuser` es el ÚNICO permiso de PLATAFORMA (los demás son de centro). NUNCA se
# concede en un flujo de "dar permisos a esta persona en su centro".
PERMISO_NO_GESTIONABLE = {"superuser"}


class AuthError(Exception):
    """Credenciales inválidas o acceso denegado."""


class AuthService:
    def __init__(self, session: Session):
        self.session = session

    # ───────────────────── auditoría ─────────────────────
    def audit(
        self, accion: str, *, usuario_id: Optional[int] = None, centro_id: Optional[int] = None,
        recurso: Optional[str] = None, detalle: Any = None, ip: Optional[str] = None,
        exito: bool = True,
    ) -> None:
        if detalle is not None:
            detalle = json.loads(json.dumps(detalle, default=str))
        self.session.add(Auditoria(
            accion=accion, usuario_id=usuario_id, centro_id=centro_id,
            recurso=recurso, detalle=detalle, ip=ip, exito=exito,
        ))
        self.session.commit()

    def _usuario_activo_por_email(self, email: str) -> Optional[Usuario]:
        hoy = date.today()
        return self.session.exec(
            select(Usuario)
            .join(UsuarioPeriodo, UsuarioPeriodo.usuario_id == Usuario.id)
            .where(
                Usuario.email == email,
                (UsuarioPeriodo.fecha_baja.is_(None)) | (UsuarioPeriodo.fecha_baja > hoy),
            )
        ).first()

    # ───────────────────── freno al fuerza bruta ─────────────────────
    def _intentos_fallidos_por_email(self, email: str) -> int:
        from domain.config.settings import settings
        desde = datetime.utcnow() - timedelta(minutes=settings.login_ventana_min)
        return len(self.session.exec(
            select(Auditoria).where(
                Auditoria.accion == "auth.login",
                Auditoria.exito == False,  # noqa: E712
                Auditoria.created_at >= desde,
                Auditoria.recurso == email,
            )
        ).all())

    # ───────────────────── login ─────────────────────
    def login(self, email: str, password: str, *, ip: Optional[str] = None) -> dict[str, Any]:
        from domain.config.settings import settings
        if settings.login_max_intentos and \
           self._intentos_fallidos_por_email(email) >= settings.login_max_intentos:
            self.audit("auth.login.bloqueado", recurso=email, ip=ip, exito=False)
            raise AuthError(
                f"Demasiados intentos fallidos. Espera {settings.login_bloqueo_min} minutos "
                "e inténtalo de nuevo."
            )
        usuario = self._usuario_activo_por_email(email)
        if not usuario or not verify_password(password, usuario.password_hash):
            self.audit("auth.login", recurso=email, ip=ip, exito=False)
            raise AuthError("Email o contraseña incorrectos")

        accesos = self.session.exec(
            select(UserCenterRole).where(UserCenterRole.usuario_id == usuario.id)
        ).all()
        accesos_payload = [
            {"centro_id": a.centro_id, "rol_id": a.rol_id} for a in accesos
        ]
        token = create_access_token({
            "sub": str(usuario.id),
            "tipo": "centro",
            "nombre": usuario.nombre,
            "accesos": accesos_payload,
        })
        self.audit("auth.login", usuario_id=usuario.id, ip=ip, exito=True)
        return {
            "access_token": token,
            "token_type": "bearer",
            "usuario": {"id": usuario.id, "nombre": usuario.nombre, "email": usuario.email},
            "accesos": accesos_payload,
        }

    # ───────────────────── recuperar contraseña ─────────────────────
    def solicitar_reset(self, email: str, base_url: str, *, ip: Optional[str] = None) -> None:
        usuario = self._usuario_activo_por_email(email)
        if not usuario:
            return  # silencioso: no revela si el email existe
        raw = secrets.token_urlsafe(32)
        pr = PasswordReset(
            usuario_id=usuario.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expira_at=datetime.utcnow() + timedelta(hours=1),
        )
        self.session.add(pr)
        self.session.commit()
        link = f"{base_url.rstrip('/')}/restablecer?token={raw}"
        html = (
            f"<p>Has solicitado restablecer tu contraseña.</p>"
            f"<p><a href='{link}'>Pulsa aquí para crear una nueva</a> (caduca en 1 hora).</p>"
            f"<p>Si no fuiste tú, ignora este mensaje.</p>"
        )
        if not send_email(self.session, usuario.email, "Restablecer contraseña", html):
            logger.warning("RESET sin SMTP — enlace para %s: %s", usuario.email, link)
        self.audit("auth.reset.solicitar", usuario_id=usuario.id, ip=ip)

    def reset_password(self, token: str, password: str, *, ip: Optional[str] = None) -> None:
        th = hashlib.sha256(token.encode()).hexdigest()
        pr = self.session.exec(
            select(PasswordReset).where(
                PasswordReset.token_hash == th, PasswordReset.usado_at == None  # noqa: E711
            )
        ).first()
        if not pr or pr.expira_at < datetime.utcnow():
            raise AuthError("Enlace inválido o caducado")
        if len(password) < 6:
            raise AuthError("La contraseña debe tener al menos 6 caracteres")
        usuario = self.session.get(Usuario, pr.usuario_id)
        usuario.password_hash = hash_password(password)
        pr.usado_at = datetime.utcnow()
        self.session.add(usuario)
        self.session.add(pr)
        self.session.commit()
        self.audit("auth.reset.completar", usuario_id=usuario.id, ip=ip)

    # ───────────────────── RBAC ─────────────────────
    def permisos_de(self, usuario_id: int, centro_id: int) -> set[str]:
        """Códigos de permiso efectivos del usuario en ese centro:
        (permisos del rol − denegados) ∪ concesiones directas."""
        directos = set(self.session.exec(
            select(Permiso.codigo)
            .join(UserCenterPermiso, UserCenterPermiso.permiso_id == Permiso.id)
            .where(UserCenterPermiso.usuario_id == usuario_id, UserCenterPermiso.centro_id == centro_id)
        ).all())
        de_rol = set(self.session.exec(
            select(Permiso.codigo)
            .join(RolePermiso, RolePermiso.permiso_id == Permiso.id)
            .join(UserCenterRole, UserCenterRole.rol_id == RolePermiso.rol_id)
            .where(UserCenterRole.usuario_id == usuario_id, UserCenterRole.centro_id == centro_id)
        ).all()) - PERMISO_NO_GESTIONABLE
        denegados = set(self.session.exec(
            select(Permiso.codigo)
            .join(UserCenterPermisoDenegado, UserCenterPermisoDenegado.permiso_id == Permiso.id)
            .where(UserCenterPermisoDenegado.usuario_id == usuario_id,
                   UserCenterPermisoDenegado.centro_id == centro_id)
        ).all())
        return directos | (de_rol - denegados)

    def tiene_acceso_a_centro(self, accesos: list[dict], centro_id: int) -> bool:
        return any(a.get("centro_id") == centro_id for a in accesos)
