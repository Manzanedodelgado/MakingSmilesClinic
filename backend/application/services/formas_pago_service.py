"""Formas de pago de pacientes: único punto de lectura del catálogo `formas_pago` (migración 040)."""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from domain.models.economico import FormaPago


def formas_pago(session: Session, *, solo_caja: bool = False) -> list[FormaPago]:
    stmt = select(FormaPago).where(FormaPago.activo == True)  # noqa: E712
    if solo_caja:
        stmt = stmt.where(FormaPago.en_caja == True)  # noqa: E712
    return list(session.exec(stmt.order_by(FormaPago.orden, FormaPago.id)).all())


def mapa_formas(session: Session) -> dict[int, FormaPago]:
    return {f.id: f for f in session.exec(select(FormaPago)).all()}


def nombre_forma(formas: dict[int, FormaPago], forma_id: Optional[int]) -> Optional[str]:
    f = formas.get(forma_id) if forma_id is not None else None
    return f.nombre if f else None


def como_dict(f: FormaPago) -> dict:
    return {"id": f.id, "nombre": f.nombre, "grupo": f.grupo}
