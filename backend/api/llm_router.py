"""LLM — análisis inteligente (Claude via OpenRouter). Diagnóstico automático, plan sugerido."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select
import json

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.audit_helper import _audit
from api.paciente_helper import _get_paciente
from domain.models.ortodoncia import CasoOrtodoncia
from infrastructure.config.db import get_session
from infrastructure.external_apis.openrouter_client import generar_diagnostico_llm
from infrastructure.external_apis.pdf_generator import generar_pdf_caso

router = APIRouter(prefix="/pacientes", tags=["llm · diagnóstico"])


class MedicionesInput(BaseModel):
    SNA: Optional[float] = None
    SNB: Optional[float] = None
    ANB: Optional[float] = None
    IMPA: Optional[float] = None
    FMA: Optional[float] = None
    Wits: Optional[float] = None
    PPM: Optional[float] = None


class DiagnosticoLLMRequest(BaseModel):
    caso_id: int
    mediciones: MedicionesInput
    notas_clinicas: Optional[str] = None


@router.post("/{paciente_id}/casos-ortodoncia/{caso_id}/generar-diagnostico")
async def generar_diagnostico(
    paciente_id: int,
    caso_id: int,
    data: DiagnosticoLLMRequest,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    """Genera diagnóstico automático usando Claude (OpenRouter)."""
    _get_paciente(session, centro_id, paciente_id)

    caso = session.get(CasoOrtodoncia, caso_id)
    if not caso or caso.centro_id != centro_id or caso.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado")

    try:
        resultado = await generar_diagnostico_llm(
            mediciones=data.mediciones.dict(exclude_none=True),
            notas=data.notas_clinicas,
        )

        caso.diagnostico_texto = resultado.get("diagnostico")
        caso.diagnostico_clase = resultado.get("clase")
        caso.diagnostico_patron = resultado.get("patron")
        session.add(caso)
        session.commit()

        _audit(
            session,
            user,
            centro_id,
            "llm.diagnostico",
            f"caso:{caso_id}",
            request,
            {"modelo": "claude-3-sonnet", "mediciones": len(data.mediciones.dict(exclude_none=True))},
        )

        return {
            "id": caso_id,
            "diagnostico": resultado.get("diagnostico"),
            "clase": resultado.get("clase"),
            "patron": resultado.get("patron"),
        }

    except Exception as e:  # raiz: OpenRouter/LLM caído o respuesta inválida -> 500 controlado
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Error LLM: {str(e)}")


@router.get("/{paciente_id}/casos-ortodoncia/{caso_id}/reporte-pdf")
async def descargar_reporte_pdf(
    paciente_id: int,
    caso_id: int,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.ver")),
    session: Session = Depends(get_session),
):
    """Descarga PDF con mediciones, diagnóstico y plan."""
    _get_paciente(session, centro_id, paciente_id)

    caso = session.get(CasoOrtodoncia, caso_id)
    if not caso or caso.centro_id != centro_id or caso.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado")

    try:
        pdf_path = await generar_pdf_caso(caso)

        _audit(
            session,
            user,
            centro_id,
            "pdf.reporte",
            f"caso:{caso_id}",
            request,
            {"formato": "PDF"},
        )

        return FileResponse(pdf_path, media_type="application/pdf", filename=f"reporte_caso_{caso_id}.pdf")

    except Exception as e:  # raiz: fallo generando el PDF (reportlab) -> 500 controlado
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Error PDF: {str(e)}")
