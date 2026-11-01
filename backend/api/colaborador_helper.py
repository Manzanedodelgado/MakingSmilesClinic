"""Selector de colaboradores activos — fuente compartida (REGLA DURA).

Los selectores NUNCA cargan ex-personal de baja: `Colaborador.activo` Y periodo
abierto (`fecha_baja` vacía) — hay activos con baja, así que `activo` solo no
basta. Y solo los de ESTE centro: el periodo es la pertenencia al centro.
"""
from sqlmodel import Session, select

from domain.models.core import Colaborador
from domain.models.identidad import Usuario, UsuarioPeriodo


def colaboradores_activos_rows(session: Session, centro_id: int) -> list:
    """Filas (colaborador, usuario, periodo) activos del centro, ordenadas por nombre."""
    return session.exec(
        select(Colaborador, Usuario, UsuarioPeriodo)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .join(Usuario, Usuario.id == UsuarioPeriodo.usuario_id)
        .where(Colaborador.activo == True, UsuarioPeriodo.fecha_baja.is_(None),  # noqa: E712
               UsuarioPeriodo.centro_id == centro_id)
        .order_by(Usuario.nombre)
    ).all()
