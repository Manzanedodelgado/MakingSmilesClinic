"""Servicio de configuración jerárquica.

Resuelve una clave eligiendo el valor MÁS ESPECÍFICO presente, recorriendo la
jerarquía plataforma → centro → sistema → usuario. CONFIG es la fuente de la verdad.
"""
from typing import Any, Optional

from sqlmodel import Session, select

from domain.models.config import Configuracion
from infrastructure.events import emit


class ConfigMissingError(KeyError):
    """La clave requerida no existe en ningún ámbito. Fallo RUIDOSO."""


class ConfigService:
    def __init__(self, session: Session):
        self.session = session

    # ───────────────────── lectura ─────────────────────
    def resolve(
        self,
        clave: str,
        *,
        centro_id: Optional[int] = None,
        sistema: Optional[str] = None,
        usuario_id: Optional[int] = None,
        default: Any = None,
    ) -> Any:
        """Valor efectivo de `clave`, del ámbito más específico al más general."""
        if self.session is None:
            return default
        rows = self.session.exec(
            select(Configuracion).where(Configuracion.clave == clave)
        ).all()

        ladder = [
            (centro_id, sistema, usuario_id),
            (centro_id, sistema, None),
            (centro_id, None, None),
            (None, sistema, None),
            (None, None, None),
        ]
        index = {(r.centro_id, r.sistema, r.usuario_id): r.valor for r in rows}
        for key in ladder:
            if key in index:
                return index[key]
        return default

    def require(self, clave: str, *, centro_id: Optional[int] = None, sistema: Optional[str] = None) -> Any:
        sentinel = object()
        value = self.resolve(clave, centro_id=centro_id, sistema=sistema, default=sentinel)
        if value is sentinel:
            raise ConfigMissingError(
                f"Config requerida ausente: clave='{clave}' centro={centro_id} sistema='{sistema}'"
            )
        return value

    def for_scope(self, *, centro_id: Optional[int], sistema: Optional[str]) -> dict[str, Any]:
        """Mapa {clave: valor} efectivo para un centro+sistema (global ⊕ centro ⊕ sistema)."""
        if self.session is None:
            return {}
        from sqlalchemy import or_

        stmt = select(Configuracion).where(Configuracion.usuario_id.is_(None))
        conds = [(Configuracion.centro_id.is_(None)) & (Configuracion.sistema.is_(None))]
        if sistema:
            conds.append((Configuracion.centro_id.is_(None)) & (Configuracion.sistema == sistema))
        if centro_id:
            conds.append((Configuracion.centro_id == centro_id) & (Configuracion.sistema.is_(None)))
        if centro_id and sistema:
            conds.append((Configuracion.centro_id == centro_id) & (Configuracion.sistema == sistema))

        rows = self.session.exec(stmt.where(or_(*conds))).all()
        result: dict[str, Any] = {}
        order = [
            (None, None),
            (None, sistema),
            (centro_id, None),
            (centro_id, sistema),
        ]
        for c, s in order:
            for r in rows:
                if r.centro_id == c and r.sistema == s:
                    result[r.clave] = r.valor
        return result

    # ───────────────────── escritura ─────────────────────
    def set(
        self,
        clave: str,
        valor: Any,
        *,
        centro_id: Optional[int] = None,
        sistema: Optional[str] = None,
        usuario_id: Optional[int] = None,
    ) -> Configuracion:
        existing = self.session.exec(
            select(Configuracion).where(
                Configuracion.clave == clave,
                Configuracion.centro_id == centro_id,
                Configuracion.sistema == sistema,
                Configuracion.usuario_id == usuario_id,
            )
        ).first()
        if existing:
            existing.valor = valor
            row = existing
        else:
            row = Configuracion(
                clave=clave, valor=valor,
                centro_id=centro_id, sistema=sistema, usuario_id=usuario_id,
            )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        emit("config.cambiada", {
            "clave": clave, "centro_id": centro_id, "sistema": sistema, "usuario_id": usuario_id,
        })
        return row
