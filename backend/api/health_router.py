"""Endpoint de salud (capa de interfaz).

El esqueleto sirve un /health autocontenido (sin BD ni LLM). M00 ampliará este router
con las comprobaciones de base de datos y proveedor LLM del contrato de paridad.
"""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Health check básico del servicio."""
    return {"status": "ok", "service": "MakingSmilesClinic API"}
