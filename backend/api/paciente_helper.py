"""Fetch de paciente con verificación multi-centro (guard anti-IDOR) — fuente compartida."""
from fastapi import HTTPException, status
from sqlmodel import Session
from domain.models.core import Paciente
from domain.models.economico import Presupuesto


def _get_paciente(session: Session, centro_id: int, paciente_id: int) -> Paciente:
    p = session.get(Paciente, paciente_id)
    if not p or p.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return p


def get_presupuesto_autorizado(session: Session, centro_id: int, paciente_id: int, pre_id: int) -> Presupuesto:
    """
    Centraliza autorización para presupuesto.
    
    Verifica:
    1. Paciente existe y pertenece al centro
    2. Presupuesto existe y pertenece al paciente y centro
    
    Retorna (paciente, presupuesto) si todas las verificaciones pasan.
    """
    paciente = _get_paciente(session, centro_id, paciente_id)
    pre = session.get(Presupuesto, pre_id)
    if not pre or pre.centro_id != centro_id or pre.paciente_id != paciente.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Presupuesto no encontrado")
    return pre
