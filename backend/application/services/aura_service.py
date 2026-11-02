"""AURA — herramientas reales de SuperUser (administración del sistema).

Su parcela (ver `domain/config/agentes.py`): SuperUser, y solo SuperUser. Todo lo que aquí
se expone es de LECTURA — Aura consulta y explica, nunca modifica nada por su cuenta. "La IA
propone, la persona dispone": cambios de configuración, usuarios o código los ejecuta una
persona por el canal habitual (paneles de Config, `gh`/despliegue…), Aura solo informa.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, func, select

from domain.models.auditoria import Auditoria
from domain.models.core import Cita, Paciente
from domain.models.economico import Presupuesto
from domain.models.identidad import Usuario, UserCenterRole


class AuraService:
    def __init__(self, session: Session, centro_id: int):
        self.s = session
        self.centro_id = centro_id

    def metricas(self) -> dict:
        """Cifras reales del centro ahora mismo — nada calculado por el LLM."""
        hoy = date.today()
        n_pacientes = self.s.exec(
            select(func.count()).select_from(Paciente).where(Paciente.centro_id == self.centro_id)
        ).one()
        n_citas_hoy = self.s.exec(
            select(func.count()).select_from(Cita).where(
                Cita.centro_id == self.centro_id, Cita.fecha == hoy)
        ).one()
        n_presu_pendientes = self.s.exec(
            select(func.count()).select_from(Presupuesto).where(
                Presupuesto.centro_id == self.centro_id, Presupuesto.estado_id.in_([0, 1]))
        ).one()
        return {
            "pacientes": n_pacientes,
            "citasHoy": n_citas_hoy,
            "presupuestosAbiertos": n_presu_pendientes,
            "fecha": hoy.isoformat(),
        }

    def auditoria(self, *, accion: Optional[str] = None, dias: int = 7, limite: int = 30) -> list[dict]:
        """Últimas acciones auditadas del centro. Filtro por texto de acción (contiene) y
        ventana de días. Nunca devuelve el `detalle` completo si contiene PII sensible más
        allá de lo mínimo — se recorta a claves, no valores, cuando el volumen es alto."""
        desde = date.today() - timedelta(days=max(1, dias))
        q = select(Auditoria).where(
            Auditoria.centro_id == self.centro_id,
            Auditoria.created_at >= desde,
        )
        if accion:
            q = q.where(Auditoria.accion.ilike(f"%{accion}%"))
        filas = self.s.exec(q.order_by(Auditoria.id.desc()).limit(min(limite, 100))).all()
        return [{
            "id": f.id, "accion": f.accion, "recurso": f.recurso, "exito": f.exito,
            "usuarioId": f.usuario_id, "fecha": f.created_at.isoformat() if f.created_at else None,
        } for f in filas]

    def usuarios_del_centro(self) -> list[dict]:
        """Quién tiene acceso a este centro ahora mismo. Solo lectura: alta/baja real se
        hace desde Config › Personal, no desde aquí."""
        filas = self.s.exec(
            select(Usuario.id, Usuario.nombre, Usuario.email)
            .join(UserCenterRole, UserCenterRole.usuario_id == Usuario.id)
            .where(UserCenterRole.centro_id == self.centro_id)
            .distinct()
        ).all()
        return [{"id": u.id, "nombre": u.nombre, "email": u.email} for u in filas]
