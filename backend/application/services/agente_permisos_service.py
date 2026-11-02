"""Sección 6 — quién puede administrar un agente."""
from sqlmodel import Session, select

from domain.models.agentes import AgentePermisoAdmin


def puede_ver(session: Session, agente_id: int, rol_o_usuario: str) -> bool:
    fila = session.exec(
        select(AgentePermisoAdmin).where(
            AgentePermisoAdmin.agente_id == agente_id, AgentePermisoAdmin.rol_o_usuario == rol_o_usuario
        )
    ).first()
    return bool(fila and fila.puede_ver)


def puede_editar(session: Session, agente_id: int, rol_o_usuario: str) -> bool:
    # SuperUser wildcard
    if rol_o_usuario in ("superuser", "admin", "user:superuser"):
        return True
    fila = session.exec(
        select(AgentePermisoAdmin).where(
            AgentePermisoAdmin.agente_id == agente_id, AgentePermisoAdmin.rol_o_usuario == rol_o_usuario
        )
    ).first()
    return bool(fila and fila.puede_editar)


def grant(session: Session, agente_id: int, rol_o_usuario: str, puede_ver: bool = True, puede_editar: bool = False) -> AgentePermisoAdmin:
    fila = session.exec(
        select(AgentePermisoAdmin).where(
            AgentePermisoAdmin.agente_id == agente_id, AgentePermisoAdmin.rol_o_usuario == rol_o_usuario
        )
    ).first()
    if fila:
        fila.puede_ver = puede_ver
        fila.puede_editar = puede_editar
    else:
        fila = AgentePermisoAdmin(agente_id=agente_id, rol_o_usuario=rol_o_usuario, puede_ver=puede_ver, puede_editar=puede_editar)
    session.add(fila)
    session.commit()
    session.refresh(fila)
    return fila
