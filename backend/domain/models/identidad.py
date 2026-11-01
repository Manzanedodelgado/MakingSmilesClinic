"""Identidad y RBAC en dos niveles.

Un solo modelo de identidad, dos niveles:

  Nivel 1 — PLATAFORMA (dueño del SaaS):   platform_users · platform_roles
  Nivel 2 — CENTRO (personal clínico):     usuarios · roles · permisos
                                           user_center_roles  (LA tabla de accesos)

Regla: el ACCESO se resuelve por `user_center_roles` (user × centro × rol), NO por un
campo `role` plano en el usuario. Superuser ≠ usuario de centro: tablas separadas.
"""
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin


# ═══════════════════ NIVEL 1 — PLATAFORMA ═══════════════════
class PlatformUser(TimestampMixin, table=True):
    """Operador del SaaS (superadmin). SEPARADO de los usuarios de centro."""
    __tablename__ = "platform_users"
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    nombre: str = Field(max_length=200)
    password_hash: str = Field(max_length=255)
    rol: str = Field(default="operador", index=True)   # operador | superadmin
    activo: bool = Field(default=True, index=True)


# ═══════════════════ NIVEL 2 — CENTRO ═══════════════════
class Usuario(TimestampMixin, table=True):
    """La PERSONA (IdStaff). Identidad fija, única — nunca se duplica."""
    __tablename__ = "usuarios"
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(max_length=120)
    apellidos: Optional[str] = Field(default=None, max_length=200)
    nif: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, index=True, max_length=255)
    username: Optional[str] = Field(default=None, index=True, max_length=120)
    password_hash: Optional[str] = Field(default=None, max_length=255)
    telefono: Optional[str] = Field(default=None, max_length=50)
    color: Optional[str] = Field(default=None, max_length=9)

    accesos: list["UserCenterRole"] = Relationship(back_populates="usuario")
    periodos: list["UsuarioPeriodo"] = Relationship(back_populates="usuario")


class UsuarioPeriodo(TimestampMixin, table=True):
    """Una etapa laboral de la persona (alta→baja). `fecha_baja` vacía = abierto."""
    __tablename__ = "usuario_periodos"
    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuarios.id", nullable=False, index=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    orden: int = Field(default=0, index=True)
    staff_tipo: Optional[str] = Field(default=None, max_length=40, index=True)
    tipo_contrato: Optional[str] = Field(default=None, max_length=40)
    fecha_alta: Optional[date] = Field(default=None)
    fecha_baja: Optional[date] = Field(default=None)
    usuario: Usuario = Relationship(back_populates="periodos")


class Rol(TimestampMixin, table=True):
    __tablename__ = "roles"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    nombre: str = Field(max_length=100)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    permisos: list["RolePermiso"] = Relationship(back_populates="rol")


class Permiso(TimestampMixin, table=True):
    """Catálogo de permisos finos."""
    __tablename__ = "permisos"
    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str = Field(unique=True, index=True, max_length=100)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    roles: list["RolePermiso"] = Relationship(back_populates="permiso")


class RolePermiso(TimestampMixin, table=True):
    """N:M rol↔permiso."""
    __tablename__ = "role_permisos"
    rol_id: int = Field(foreign_key="roles.id", primary_key=True, index=True)
    permiso_id: int = Field(foreign_key="permisos.id", primary_key=True, index=True)
    rol: Rol = Relationship(back_populates="permisos")
    permiso: Permiso = Relationship(back_populates="roles")


class UserCenterRole(TimestampMixin, table=True):
    """La tabla de ACCESOS (membresía): usuario × centro."""
    __tablename__ = "user_center_roles"
    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuarios.id", nullable=False, index=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    rol_id: int = Field(foreign_key="roles.id", nullable=False, index=True)
    usuario: Usuario = Relationship(back_populates="accesos")


class UserCenterPermiso(TimestampMixin, table=True):
    """Permisos efectivos por persona (concesión directa): usuario × centro × permiso."""
    __tablename__ = "user_center_permisos"
    usuario_id: int = Field(foreign_key="usuarios.id", primary_key=True, index=True)
    centro_id: int = Field(foreign_key="centros.id", primary_key=True, index=True)
    permiso_id: int = Field(foreign_key="permisos.id", primary_key=True, index=True)


class UserCenterPermisoDenegado(TimestampMixin, table=True):
    """Límites por persona: permisos que su rol concede pero a esta persona se le quitan."""
    __tablename__ = "user_center_permisos_denegados"
    usuario_id: int = Field(foreign_key="usuarios.id", primary_key=True, index=True)
    centro_id: int = Field(foreign_key="centros.id", primary_key=True, index=True)
    permiso_id: int = Field(foreign_key="permisos.id", primary_key=True, index=True)


# ═══════════════════ NAVEGACIÓN / ACCESO POR SISTEMA Y ÁREA ═══════════════════
class Sistema(TimestampMixin, table=True):
    """Sistema del organismo (CUIDARTE, ESCÚCHARTE, GESTIÓNALO, IA, Configuración, SuperUser)."""
    __tablename__ = "sistemas"
    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str = Field(unique=True, index=True, max_length=40)
    nombre: str = Field(max_length=80)
    orden: Optional[int] = Field(default=None)
    activo: bool = Field(default=True, index=True)
    areas: list["Area"] = Relationship(back_populates="sistema")


class Area(TimestampMixin, table=True):
    """Sección de la app (pantalla). Pertenece a un sistema."""
    __tablename__ = "areas"
    id: Optional[int] = Field(default=None, primary_key=True)
    sistema_id: int = Field(foreign_key="sistemas.id", nullable=False, index=True)
    codigo: str = Field(index=True, max_length=40)
    nombre: str = Field(max_length=80)
    ruta: Optional[str] = Field(default=None, max_length=120)
    icono: Optional[str] = Field(default=None, max_length=60)
    orden: Optional[int] = Field(default=None)
    activo: bool = Field(default=True, index=True)
    sistema: Sistema = Relationship(back_populates="areas")


class RolArea(TimestampMixin, table=True):
    """Acceso de un rol a un área (qué pantallas ve cada rol)."""
    __tablename__ = "rol_area"
    rol_id: int = Field(foreign_key="roles.id", primary_key=True, index=True)
    area_id: int = Field(foreign_key="areas.id", primary_key=True, index=True)


class PasswordReset(TimestampMixin, table=True):
    """Token de recuperación de contraseña (un solo uso, con caducidad)."""
    __tablename__ = "password_resets"
    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuarios.id", nullable=False, index=True)
    token_hash: str = Field(index=True, max_length=255)
    expira_at: datetime = Field(index=True)
    usado_at: Optional[datetime] = Field(default=None)
