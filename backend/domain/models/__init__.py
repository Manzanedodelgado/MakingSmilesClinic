"""Registro de modelos de dominio para SQLModel.metadata."""
from domain.models.core import Centro, CentroBase, Colaborador
from domain.models.identidad import (
    PlatformUser, Usuario, UsuarioPeriodo, Rol, Permiso, RolePermiso,
    UserCenterRole, UserCenterPermiso, UserCenterPermisoDenegado,
    Sistema, Area, RolArea, PasswordReset,
)
from domain.models.config import Configuracion, Integracion
from domain.models.auditoria import Auditoria

__all__ = [
    "Centro", "CentroBase", "Colaborador",
    "PlatformUser", "Usuario", "UsuarioPeriodo", "Rol", "Permiso", "RolePermiso",
    "UserCenterRole", "UserCenterPermiso", "UserCenterPermisoDenegado",
    "Sistema", "Area", "RolArea", "PasswordReset",
    "Configuracion", "Integracion", "Auditoria",
]
