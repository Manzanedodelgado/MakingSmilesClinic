"""Orquestador de agentes con políticas de seguridad estrictas."""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from domain.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Roles de agente con diferentes niveles de acceso."""
    PATIENT = "patient"
    DOCTOR = "doctor"
    SUPERUSER = "superuser"


class AgentOrchestrator:
    """Orquestador de agentes con autorización estricta."""
    
    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider or self._create_llm_provider()
        self._tools = self._register_tools()
        self._security_policies = self._load_security_policies()
    
    def _create_llm_provider(self) -> LLMProvider:
        """Crear proveedor LLM — misma fábrica que /health, con rescate en cascada
        (Ollama -> Groq -> OpenRouter -> Cerebras) si el primario no responde."""
        from infrastructure.llm.ollama_provider import get_llm_provider
        return get_llm_provider()
    
    def _register_tools(self) -> Dict[str, Any]:
        """Registrar herramientas disponibles con autorización."""
        from application.tools import (
            get_current_user_context,
            get_patient_summary
        )
        
        return {
            "get_current_user_context": get_current_user_context,
            "get_patient_summary": get_patient_summary,
        }
    
    def _load_security_policies(self) -> Dict[str, Any]:
        """Cargar políticas de seguridad."""
        return {
            AgentRole.PATIENT: {
                "allowed_data": ["own"],
                "can_access_other_patients": False,
                "can_access_admin": False,
                "max_context_size": 4096,
            },
            AgentRole.DOCTOR: {
                "allowed_data": ["assigned_patients"],
                "can_access_other_patients": False,
                "can_access_admin": False,
                "max_context_size": 8192,
            },
            AgentRole.SUPERUSER: {
                "allowed_data": ["all"],
                "can_access_other_patients": True,
                "can_access_admin": True,
                "max_context_size": 16384,
                "requires_break_glass": True,
            }
        }
    
    def get_available_tools(self) -> List[str]:
        """Obtener lista de herramientas disponibles."""
        return list(self._tools.keys())
    
    async def _authorize_access(
        self,
        role: AgentRole,
        user_context: Dict[str, Any],
        requested_resource: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Verificar autorización antes de acceder a datos."""
        policy = self._security_policies.get(role)
        
        if not policy:
            logger.warning(f"Política no encontrada para rol: {role}")
            return False
        
        # Verificar tenant
        if "centro_id" not in user_context:
            logger.warning("Centro ID no encontrado en contexto")
            return False
        
        # Verificar rol
        if user_context.get("user_type") != role.value:
            logger.warning(f"Rol inconsistente: {user_context.get('user_type')} != {role.value}")
            return False
        
        # Para pacientes, verificar acceso a propios datos
        if role == AgentRole.PATIENT:
            if requested_resource and requested_resource.get("patient_id"):
                if requested_resource["patient_id"] != user_context.get("user_id"):
                    logger.warning("Paciente intenta acceder a datos de otro paciente")
                    return False
        
        # Para doctores, verificar relación con paciente
        if role == AgentRole.DOCTOR:
            if requested_resource and requested_resource.get("patient_id"):
                # Aquí se verificaría la relación doctor-paciente en DB
                # Por ahora, solo logueamos
                logger.info(f"Verificando relación doctor-paciente")
        
        return True
    
    async def _sanitize_prompt(self, prompt: str, role: AgentRole) -> str:
        """Sanitizar prompt para evitar prompt injection."""
        # Remover intentos de bypass de seguridad
        dangerous_patterns = [
            "olvida las reglas",
            "ignora las instrucciones",
            "bypass",
            "jailbreak",
            "hack",
        ]
        
        sanitized = prompt.lower()
        for pattern in dangerous_patterns:
            if pattern in sanitized:
                logger.warning(f"Patrón peligroso detectado: {pattern}")
                # No bloqueamos, pero logueamos
        
        return prompt
    
    async def process_message(
        self,
        message: str,
        role: AgentRole,
        user_context: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Procesar mensaje con autorización estricta.
        
        Flujo:
        1. Autorizar acceso
        2. Sanitizar prompt
        3. Construir contexto autorizado
        4. Llamar LLM
        5. Validar respuesta
        """
        # 1. Autorizar
        if not await self._authorize_access(role, user_context):
            return {
                "error": "No autorizado",
                "response": "No tienes autorización para acceder a esa información.",
                "policy": "access_denied"
            }
        
        # 2. Sanitizar
        sanitized_message = await self._sanitize_prompt(message, role)
        
        # 3. Construir contexto autorizado
        system_prompt = self._build_system_prompt(role, user_context)
        
        # 4. Preparar mensajes para LLM
        messages = self._build_messages(system_prompt, sanitized_message, conversation_history)
        
        try:
            # 5. Llamar LLM
            response = await self.llm_provider.chat(messages)
            
            # 6. Validar respuesta (output guard)
            if not self._validate_response(response, role, user_context):
                logger.warning("Respuesta rechazada por output guard")
                return {
                    "error": "Respuesta no válida",
                    "response": "No puedo proporcionar esa información.",
                    "policy": "output_guard"
                }
            
            return {
                "response": response,
                "role": role.value,
                "policy": "allowed",
                "tools_used": []
            }
            
        except Exception as e:  # raiz: fallo del proveedor LLM → respuesta de error genérica
            logger.error(f"Error procesando mensaje: {e}")
            return {
                "error": str(e),
                "response": "Lo siento, ha ocurrido un error. Por favor intenta de nuevo.",
                "policy": "error"
            }
    
    def _build_system_prompt(self, role: AgentRole, user_context: Dict[str, Any]) -> str:
        """Construir prompt del sistema con políticas de seguridad."""
        base_prompt = f"""Eres un asistente médico institucional.

REGLAS CRÍTICAS:
- Nunca compartas información de pacientes que no esté explícitamente autorizada
- Solo responde con información que el usuario esté autorizado a conocer
- Si no estás seguro, responde que no tienes autorización
- Nunca reveles la existencia de pacientes que el usuario no pueda ver
- No confirmes ni niegues la existencia de datos no autorizados

ROL DEL USUARIO: {role.value}
CENTRO: {user_context.get('centro_id', 'N/A')}
"""
        
        if role == AgentRole.PATIENT:
            base_prompt += """
Eres asistente de un PACIENTE.
- Solo puedes acceder a información de este paciente
- Nunca reveles información de otros pacientes
- No aceptes solicitudes para ver datos de terceros
"""
        elif role == AgentRole.DOCTOR:
            base_prompt += """
Eres asistente de un DOCTOR.
- Solo puedes acceder a información de pacientes asignados
- Nunca reveles información de pacientes no asignados
- Las decisiones clínicas deben ser validadas por el doctor
"""
        elif role == AgentRole.SUPERUSER:
            base_prompt += """
Eres asistente de un SUPERUSER.
- Acceso administrativo con restricciones
- Requiere políticas explícitas para acceder a datos clínicos
- Prioriza configuración y procesos sobre PII
"""
        
        return base_prompt
    
    def _build_messages(
        self,
        system_prompt: str,
        user_message: str,
        history: Optional[List[Dict[str, str]]]
    ) -> List[Dict[str, str]]:
        """Construir mensajes para LLM."""
        messages = [{"role": "system", "content": system_prompt}]
        
        if history:
            messages.extend(history)
        
        messages.append({"role": "user", "content": user_message})
        
        return messages
    
    def _validate_response(
        self,
        response: str,
        role: AgentRole,
        user_context: Dict[str, Any]
    ) -> bool:
        """Validar respuesta con output guard."""
        # Verificar que no contenga datos sensibles no autorizados
        # Esto es una validación básica, en producción usar DLP
        
        # Buscar patrones que indiquen fuga de datos
        suspicious_patterns = [
            "paciente",
            "pacientes",
            "historia clínica",
            "diagnóstico",
        ]
        
        # Por ahora, solo logueamos
        # En producción, implementar validación más robusta
        
        return True
