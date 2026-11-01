"""Seed de desarrollo para M01/M02.

Idempotente (si ya hay un centro, no hace nada). Crea:
  - 1 operador de plataforma (superadmin)
  - 1 centro
  - catálogo de permisos finos + rol Administrador con todos
  - 1 usuario de centro con ese rol y concesiones directas
  - config de ejemplo (global + centro + sistema)

Credenciales dev: admin@makingsmiles.local / admin1234
"""
from datetime import date

from sqlmodel import Session, select

from domain.models.config import Configuracion
from domain.models.core import Centro
from domain.models.identidad import (
    Permiso, PlatformUser, Rol, RolePermiso, Usuario, UserCenterPermiso,
    UserCenterRole, UsuarioPeriodo,
)
from infrastructure.security import hash_password

PERMISOS = [
    ("config.ver", "Ver configuración"),
    ("config.editar", "Editar configuración"),
    ("pacientes.ver", "Ver pacientes"),
    ("pacientes.editar", "Crear/editar pacientes"),
    ("citas.ver", "Ver agenda"),
    ("citas.editar", "Crear/editar citas"),
    ("comunicacion.ver", "Ver comunicación / WhatsApp"),
    ("comunicacion.editar", "Enviar mensajes y configurar WhatsApp"),
    ("gestoria.ver", "Ver gestoría / contabilidad"),
    ("gestoria.editar", "Crear/editar gestoría"),
    ("informes.ver", "Ver / ejecutar informes"),
    ("informes.editar", "Crear / guardar / borrar informes"),
]


def seed_dev(session: Session) -> None:
    if session.exec(select(Centro)).first():
        return  # ya sembrado

    session.add(PlatformUser(
        email="root@makingsmiles.local", nombre="Root Plataforma",
        password_hash=hash_password("root1234"), rol="superadmin",
    ))

    centro = Centro(
        nombre="Rubio García Dental", codigo="RGD",
        direccion="C/ Mayor 19", cp="28921", poblacion="Alcorcón", provincia="Madrid",
        telefono="916410841", telefono_movil="664218253",
        email="info@rubiogarciadental.com", web="www.rubiogarciadental.com",
        instagram="@rubiogarciadental", num_gabinetes=2,
    )
    session.add(centro)
    session.commit()
    session.refresh(centro)

    permisos = [Permiso(codigo=c, descripcion=d) for c, d in PERMISOS]
    session.add_all(permisos)
    session.commit()
    for p in permisos:
        session.refresh(p)

    rol_admin = Rol(centro_id=centro.id, nombre="Administrador", descripcion="Acceso total al centro")
    session.add(rol_admin)
    session.commit()
    session.refresh(rol_admin)
    session.add_all([RolePermiso(rol_id=rol_admin.id, permiso_id=p.id) for p in permisos])

    usuario = Usuario(
        email="admin@makingsmiles.local", nombre="Admin Demo",
        password_hash=hash_password("admin1234"),
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    session.add(UserCenterRole(usuario_id=usuario.id, centro_id=centro.id, rol_id=rol_admin.id))
    session.add_all([UserCenterPermiso(usuario_id=usuario.id, centro_id=centro.id, permiso_id=p.id)
                     for p in permisos])
    session.add(UsuarioPeriodo(
        usuario_id=usuario.id, centro_id=centro.id, orden=0,
        staff_tipo="ADMINISTRADOR", fecha_alta=date(2026, 1, 1),
    ))

    session.add_all([
        Configuracion(clave="marca.nombre", valor="MakingSmiles"),
        Configuracion(clave="marca.nombre", valor="Clínica Demo", centro_id=centro.id),
        Configuracion(clave="agenda.intervalo_min", valor=15, centro_id=centro.id, sistema="cuidarte"),
    ])
    session.commit()
