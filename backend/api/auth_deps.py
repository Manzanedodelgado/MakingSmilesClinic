"""Dependencias de autenticación y autorización (capa de interfaz).

Toda ruta protegida pasa por aquí:
  - get_current_user  → valida el JWT y entrega el contexto del usuario.
  - get_current_centro → exige cabecera X-Centro-Id y verifica acceso multi-tenant.
  - require_permission("codigo") → 403 si el usuario no tiene ese permiso fino.
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from application.services.auth_service import AuthService
from infrastructure.config.db import get_session
from infrastructure.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, usuario_id: int, nombre: str, accesos: list[dict]):
        self.usuario_id = usuario_id
        self.nombre = nombre
        self.accesos = accesos


def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> CurrentUser:
    token = creds.credentials if creds else request.cookies.get("access_token")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")
    payload = decode_access_token(token)
    if not payload or payload.get("tipo") != "centro":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado")
    return CurrentUser(
        usuario_id=int(payload["sub"]),
        nombre=payload.get("nombre", ""),
        accesos=payload.get("accesos", []),
    )


def get_current_centro(
    x_centro_id: Optional[int] = Header(default=None, alias="X-Centro-Id"),
    user: CurrentUser = Depends(get_current_user),
) -> int:
    """Centro activo de la petición. Multi-tenant: el usuario DEBE tener acceso."""
    if x_centro_id is None:
        if len(user.accesos) == 1:
            return user.accesos[0]["centro_id"]
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Indica el centro en la cabecera X-Centro-Id",
        )
    if not any(a.get("centro_id") == x_centro_id for a in user.accesos):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin acceso a ese centro")
    return x_centro_id


def require_permission(codigo: str):
    """Factoría de dependencia: exige el permiso `codigo` en el centro activo."""
    def _dep(
        user: CurrentUser = Depends(get_current_user),
        centro_id: int = Depends(get_current_centro),
        session: Session = Depends(get_session),
    ) -> CurrentUser:
        permisos = AuthService(session).permisos_de(user.usuario_id, centro_id)
        if codigo not in permisos:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Permiso requerido: {codigo}",
            )
        return user
    return _dep


def require_any_permission(*codigos: str):
    """Factoría de dependencia: exige AL MENOS UNO de `codigos` (OR) en el centro activo."""
    def _dep(
        user: CurrentUser = Depends(get_current_user),
        centro_id: int = Depends(get_current_centro),
        session: Session = Depends(get_session),
    ) -> CurrentUser:
        permisos = AuthService(session).permisos_de(user.usuario_id, centro_id)
        if not any(c in permisos for c in codigos):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Permiso requerido: uno de {list(codigos)}",
            )
        return user
    return _dep
