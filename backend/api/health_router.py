"""Endpoints de salud / diagnóstico (capa de interfaz)."""
from fastapi import APIRouter, Depends
from sqlmodel import Session, text

from infrastructure.config.db import get_session
from infrastructure.llm.ollama_provider import get_llm_provider


router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Health check completo del sistema."""
    # Check database
    db_status = "ok"
    try:
        session = next(get_session())
        session.exec(text("SELECT 1"))
        session.close()
    except Exception:  # raiz: sin BD -> estado 'error' en /health; el endpoint sigue respondiendo al balanceador
        db_status = "error"
    
    # Check LLM provider
    llm_provider = get_llm_provider()
    llm_health = await llm_provider.health_check()
    
    api_status = "ok"
    
    return {
        "api": api_status,
        "database": db_status,
        "llm": llm_health.get("status", "error"),
        "provider": llm_health.get("provider", "unknown"),
        "model": llm_health.get("model", "unknown"),
        "details": {
            "llm": llm_health.get("details", {})
        }
    }


@router.get("/health/db")
def health_db(session: Session = Depends(get_session)) -> dict:
    session.exec(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}


@router.get("/health/llm")
async def health_llm() -> dict:
    """Health check específico del LLM."""
    llm_provider = get_llm_provider()
    return await llm_provider.health_check()
