"""Herramientas del agente con autorización estricta.

Principios:
- El LLM NUNCA puede pasar user_id como autoridad
- La identidad viene de la sesión autenticada
- Autorización se ejecuta ANTES de consultar datos
- NUNCA conectamos directamente a PostgreSQL
- Siempre via API interna autorizada
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Cliente API interna - se inicializa con config
_internal_api_client = None


def init_internal_api(client):
    """Inicializar cliente API interna."""
    global _internal_api_client
    _internal_api_client = client


class ToolError(Exception):
    """Error en ejecución de herramienta."""
    pass


async def get_current_user_context() -> Dict[str, Any]:
    """
    Obtener contexto del usuario actual.
    
    IMPORTANTE: Este contexto viene de la sesión autenticada,
    NUNCA del LLM.
    """
    # En producción, esto vendría de la sesión JWT
    # Por ahora, simulamos
    return {
        "user_id": "user_123",
        "user_type": "doctor",  # patient, doctor, superuser
        "centro_id": "centro_001",
        "tenant_id": "tenant_001",
    }


async def get_patient_summary(
    patient_id: int,
    user_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Obtener resumen de paciente con autorización.
    
    FLUJO:
    1. Verificar contexto de usuario
    2. Verificar autorización (RBAC + ABAC)
    3. Consultar API interna (NO PostgreSQL directo)
    4. Retornar datos autorizados
    
    EL LLM NUNCA VE DATOS NO AUTORIZADOS.
    """
    if user_context is None:
        user_context = await get_current_user_context()
    
    # Verificación de autorización
    if not _check_authorization(user_context, patient_id):
        logger.warning(
            f"Acceso denegado: user {user_context.get('user_id')} "
            f"intenta acceder a paciente {patient_id}"
        )
        return {
            "error": "Acceso denegado",
            "message": "No tienes autorización para acceder a este paciente"
        }
    
    # Consultar API interna (NUNCA PostgreSQL directo)
    if _internal_api_client:
        data = await _internal_api_client.get_patient_summary(
            patient_id, user_context
        )
        if data:
            return data
    
    # Simulación para desarrollo
    return {
        "patient_id": patient_id,
        "name": "Juan Pérez",
        "age": 35,
        "authorized": True,
        "user_context": {
            "user_id": user_context.get("user_id"),
            "user_type": user_context.get("user_type"),
        }
    }
    """
    Herramienta: get_patient_summary
    
    Reglas de autorización:
    - PATIENT: solamente su propio patient_id
    - DOCTOR: solamente patient_id de pacientes asignados
    - SUPERUSER: según policy
    """
    # Verificar autorización ANTES de consultar datos
    if user.type == "patient":
        # Paciente solo puede ver su propio contexto
        # En producción, mapear user.id -> paciente_id
        if user.id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado: paciente solo puede ver su propio contexto"
            )
    
    elif user.type == "doctor":
        # Doctor solo puede ver pacientes asignados
        # Verificar asignación
        paciente = session.get(Paciente, patient_id)
        if not paciente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Paciente no encontrado"
            )
        
        # Verificar que el doctor está asignado a este paciente
        # Lógica simplificada - en producción verificar relación doctor-paciente
        if paciente.centro_id != user.centro_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado: paciente no pertenece a tu centro"
            )
    
    elif user.type == "superuser":
        # SuperUser puede ver según policy
        # Verificar policy adicional si necesario
        pass
    
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tipo de usuario no autorizado"
        )
    
    # Solo ahora consultar datos
    paciente = session.get(Paciente, patient_id)
    if not paciente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paciente no encontrado"
        )
    
    # Devolver resumen autorizado (sin datos clínicos reales en MVP)
    return {
        "patient_id": paciente.id,
        "centro_id": paciente.centro_id,
        "name": paciente.nombre,
        "email": paciente.email if user.type != "doctor" else None,
        "status": "active",
        "authorized": True,
        "accessed_by": user.id,
        "accessed_by_type": user.type,
    }


async def get_current_user_context_tool(
    user: CurrentUser,
    session: Session,
) -> dict[str, Any]:
    """Wrapper para uso en agente."""
    return await get_current_user_context(user, session)


async def get_patient_summary_tool(
    patient_id: int,
    user: CurrentUser,
    session: Session,
) -> dict[str, Any]:
    """Wrapper para uso en agente."""
    return await get_patient_summary(patient_id, user, session)
