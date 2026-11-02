"""
Configuración del Modelo IA Multimodal para Gestor IA (Facturación).

Usa OpenRouter para acceder a Gemini 2.5 Flash (multimodal nativo: PDF, imagen, texto)
con function calling y 1M tokens de contexto. Gratuito en tier free.
"""

from typing import Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModeloMultimodalConfig:
    """Configuración del modelo IA multimodal por centro."""
    
    # Proveedor y modelo
    proveedor: str = "openrouter"           # openrouter | nvidia | mistral | direct…
    # Dirección del proveedor (OpenAI-compatible). Estaba fija en el código y por eso no se
    # podía cambiar de proveedor sin tocarlo (jmd, 18-oct-2026).
    base_url: str = "https://openrouter.ai/api/v1"
    modelo: str = "google/gemini-2.5-flash" # Modelo multimodal nativo
    # Lo que haya que añadir al cuerpo de la petición para ese modelo. Con el nemotron de
    # NVIDIA, {"chat_template_kwargs": {"enable_thinking": False}} lo deja en 2 s y 72 tokens
    # en vez de 9 s y 830, con el mismo resultado.
    extra_body: dict = field(default_factory=dict)
    
    # Parámetros de generación
    temperature: float = 0.0                # Determinístico para extracción contable
    max_tokens: int = 8192                  # Suficiente para facturas complejas + razonamiento
    top_p: float = 1.0
    
    # Timeouts
    timeout_segundos: int = 60              # Gemini 2.5 Flash es rápido
    max_reintentos: int = 3
    
    # Configuración multimodal
    soporta_pdf_nativo: bool = True         # Gemini 2.5 Flash acepta PDF directo
    soporta_imagenes: bool = True           # JPG, PNG, WebP
    max_archivos_por_peticion: int = 10     # Límite práctico
    max_tamano_mb: int = 20                 # Límite OpenRouter
    
    # Function calling / Structured output
    usar_structured_output: bool = True     # response_schema nativo
    strict_mode: bool = True                # Validación estricta de schema
    
    # Prompt versionado
    prompt_version: str = "1.0"             # Para auditoría: qué prompt usó cada extracción
    system_prompt_hash: str = ""            # Hash del SYSTEM_PROMPT usado
    
    # Few-shots
    incluir_few_shots: bool = True
    max_few_shots: int = 8                  # Los 8 casos representativos
    
    # Costes/límites (monitoring)
    max_tokens_entrada_por_dia: int = 500_000
    max_peticiones_por_minuto: int = 60
    
    # Suplente: se usa si el principal falla (p. ej. la GPU de casa apagada). Los campos
    # existían y NADIE los usaba; ahora los recorre _llamar_ia_multimodal.
    modelo_fallback: str = "google/gemini-2.5-flash-lite"  # Si falla el principal
    proveedor_fallback: str = "openrouter"
    base_url_fallback: str = ""             # vacío = la del principal
    api_key_fallback: str = ""              # vacío = la del principal
    extra_body_fallback: dict = field(default_factory=dict)
    usar_structured_output_fallback: bool = False


# Configuración por defecto (se puede override por centro en BD)
DEFAULT_CONFIG = ModeloMultimodalConfig()

# Modelos disponibles en OpenRouter (multimodales, gratuitos/baratos)
MODELOS_DISPONIBLES = {
    "google/gemini-2.5-flash": {
        "nombre": "Gemini 2.5 Flash",
        "multimodal": True,
        "pdf_nativo": True,
        "contexto_tokens": 1_000_000,
        "gratuito": True,
        "function_calling": True,
        "structured_output": True,
        "velocidad": "muy_rapida",
        "calidad_extraccion": "excelente"
    },
    "google/gemini-2.5-flash-lite": {
        "nombre": "Gemini 2.5 Flash Lite",
        "multimodal": True,
        "pdf_nativo": True,
        "contexto_tokens": 1_000_000,
        "gratuito": True,
        "function_calling": True,
        "structured_output": True,
        "velocidad": "ultra_rapida",
        "calidad_extraccion": "muy_buena"
    },
    "google/gemini-2.5-pro": {
        "nombre": "Gemini 2.5 Pro",
        "multimodal": True,
        "pdf_nativo": True,
        "contexto_tokens": 2_000_000,
        "gratuito": False,  # Tier pago
        "function_calling": True,
        "structured_output": True,
        "velocidad": "media",
        "calidad_extraccion": "excepcional"
    },
    "anthropic/claude-3.5-sonnet": {
        "nombre": "Claude 3.5 Sonnet",
        "multimodal": True,
        "pdf_nativo": False,  # Requiere conversión a imagen
        "contexto_tokens": 200_000,
        "gratuito": False,
        "function_calling": True,
        "structured_output": True,
        "velocidad": "rapida",
        "calidad_extraccion": "excelente"
    },
    "openai/gpt-4o": {
        "nombre": "GPT-4o",
        "multimodal": True,
        "pdf_nativo": False,
        "contexto_tokens": 128_000,
        "gratuito": False,
        "function_calling": True,
        "structured_output": True,
        "velocidad": "rapida",
        "calidad_extraccion": "excelente"
    },
    "openai/gpt-4o-mini": {
        "nombre": "GPT-4o Mini",
        "multimodal": True,
        "pdf_nativo": False,
        "contexto_tokens": 128_000,
        "gratuito": False,  # Muy barato
        "function_calling": True,
        "structured_output": True,
        "velocidad": "muy_rapida",
        "calidad_extraccion": "muy_buena"
    }
}


def obtener_config_centro(centro_id: int, session) -> ModeloMultimodalConfig:
    """
    Obtiene la configuración del modelo multimodal para un centro.
    Busca en integraciones (tipo='llm', agente='gestor_multimodal').
    Si no existe, usa DEFAULT_CONFIG.
    """
    from sqlmodel import select
    from domain.models.config import Integracion
    
    integracion = session.exec(select(Integracion).where(
        Integracion.centro_id == centro_id,
        Integracion.tipo == "llm",
        Integracion.agente == "gestor_multimodal",
        Integracion.activo == True
    )).first()
    
    if not integracion or not integracion.config:
        return DEFAULT_CONFIG
    
    cfg_dict = integracion.config
    return ModeloMultimodalConfig(
        base_url=cfg_dict.get("base_url", DEFAULT_CONFIG.base_url),
        extra_body=cfg_dict.get("extra_body") or {},
        proveedor=cfg_dict.get("proveedor", DEFAULT_CONFIG.proveedor),
        modelo=cfg_dict.get("modelo", DEFAULT_CONFIG.modelo),
        temperature=cfg_dict.get("temperature", DEFAULT_CONFIG.temperature),
        max_tokens=cfg_dict.get("max_tokens", DEFAULT_CONFIG.max_tokens),
        timeout_segundos=cfg_dict.get("timeout_segundos", DEFAULT_CONFIG.timeout_segundos),
        max_reintentos=cfg_dict.get("max_reintentos", DEFAULT_CONFIG.max_reintentos),
        soporta_pdf_nativo=cfg_dict.get("soporta_pdf_nativo", DEFAULT_CONFIG.soporta_pdf_nativo),
        soporta_imagenes=cfg_dict.get("soporta_imagenes", DEFAULT_CONFIG.soporta_imagenes),
        max_archivos_por_peticion=cfg_dict.get("max_archivos_por_peticion", DEFAULT_CONFIG.max_archivos_por_peticion),
        max_tamano_mb=cfg_dict.get("max_tamano_mb", DEFAULT_CONFIG.max_tamano_mb),
        usar_structured_output=cfg_dict.get("usar_structured_output", DEFAULT_CONFIG.usar_structured_output),
        strict_mode=cfg_dict.get("strict_mode", DEFAULT_CONFIG.strict_mode),
        prompt_version=cfg_dict.get("prompt_version", DEFAULT_CONFIG.prompt_version),
        system_prompt_hash=cfg_dict.get("system_prompt_hash", DEFAULT_CONFIG.system_prompt_hash),
        incluir_few_shots=cfg_dict.get("incluir_few_shots", DEFAULT_CONFIG.incluir_few_shots),
        max_few_shots=cfg_dict.get("max_few_shots", DEFAULT_CONFIG.max_few_shots),
        max_tokens_entrada_por_dia=cfg_dict.get("max_tokens_entrada_por_dia", DEFAULT_CONFIG.max_tokens_entrada_por_dia),
        max_peticiones_por_minuto=cfg_dict.get("max_peticiones_por_minuto", DEFAULT_CONFIG.max_peticiones_por_minuto),
        modelo_fallback=cfg_dict.get("modelo_fallback", DEFAULT_CONFIG.modelo_fallback),
        proveedor_fallback=cfg_dict.get("proveedor_fallback", DEFAULT_CONFIG.proveedor_fallback),
        base_url_fallback=cfg_dict.get("base_url_fallback", ""),
        api_key_fallback=cfg_dict.get("api_key_fallback", ""),
        extra_body_fallback=cfg_dict.get("extra_body_fallback") or {},
        usar_structured_output_fallback=cfg_dict.get("usar_structured_output_fallback", False),
    )


def guardar_config_centro(centro_id: int, config: ModeloMultimodalConfig, session) -> None:
    """Guarda la configuración del modelo multimodal para un centro."""
    from sqlmodel import select
    from domain.models.config import Integracion
    from domain.config.ia_multimodal import MODELOS_DISPONIBLES
    
    # Validar que el modelo existe
    if config.modelo not in MODELOS_DISPONIBLES:
        raise ValueError(f"Modelo '{config.modelo}' no está en MODELOS_DISPONIBLES")
    
    modelo_info = MODELOS_DISPONIBLES[config.modelo]
    if not modelo_info["multimodal"]:
        raise ValueError(f"Modelo '{config.modelo}' no es multimodal")
    
    # Calcular hash del system prompt actual
    import hashlib
    from domain.prompts.gasto_multimodal import SYSTEM_PROMPT
    prompt_hash = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:16]
    
    integracion = session.exec(select(Integracion).where(
        Integracion.centro_id == centro_id,
        Integracion.tipo == "llm",
        Integracion.agente == "gestor_multimodal"
    )).first()
    
    config_dict = {
        "proveedor": config.proveedor,
        "modelo": config.modelo,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout_segundos": config.timeout_segundos,
        "max_reintentos": config.max_reintentos,
        "soporta_pdf_nativo": config.soporta_pdf_nativo,
        "soporta_imagenes": config.soporta_imagenes,
        "max_archivos_por_peticion": config.max_archivos_por_peticion,
        "max_tamano_mb": config.max_tamano_mb,
        "usar_structured_output": config.usar_structured_output,
        "strict_mode": config.strict_mode,
        "prompt_version": config.prompt_version,
        "system_prompt_hash": prompt_hash,
        "incluir_few_shots": config.incluir_few_shots,
        "max_few_shots": config.max_few_shots,
        "max_tokens_entrada_por_dia": config.max_tokens_entrada_por_dia,
        "max_peticiones_por_minuto": config.max_peticiones_por_minuto,
        "modelo_fallback": config.modelo_fallback,
        "proveedor_fallback": config.proveedor_fallback,
    }
    
    if integracion:
        integracion.config = config_dict
        integracion.activo = True
    else:
        integracion = Integracion(
            centro_id=centro_id,
            tipo="llm",
            agente="gestor_multimodal",
            config=config_dict,
            activo=True
        )
        session.add(integracion)
    
    session.commit()


def validar_acceso_openrouter(api_key: str) -> bool:
    """Verifica que la API key de OpenRouter funciona y tiene acceso a Gemini 2.5 Flash."""
    import httpx
    
    try:
        response = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if response.status_code != 200:
            return False
        
        models = response.json().get("data", [])
        model_ids = [m.get("id") for m in models]
        return "google/gemini-2.5-flash" in model_ids
    except Exception:  # raiz: validacion de la config multimodal falla (red/HTTP/JSON) -> False y se usa la config por defecto
        logger.warning("multimodal: validación de config falló", exc_info=True)
        return False



def credenciales_centro(centro_id: int, session) -> tuple[Optional[str], str]:
    """(clave, dirección) del proveedor multimodal de un centro.

    Acepta `api_key` (cualquier proveedor) y el `openrouter_api_key` histórico."""
    from sqlmodel import select
    from domain.models.config import Integracion

    ig = session.exec(select(Integracion).where(
        Integracion.centro_id == centro_id,
        Integracion.tipo == "llm",
        Integracion.agente == "gestor_multimodal",
        Integracion.activo == True,  # noqa: E712
    )).first()
    cfg = (ig.config or {}) if ig else {}
    clave = cfg.get("api_key") or cfg.get("openrouter_api_key")
    return clave, cfg.get("base_url") or DEFAULT_CONFIG.base_url


__all__ = [
    "ModeloMultimodalConfig",
    "DEFAULT_CONFIG",
    "MODELOS_DISPONIBLES",
    "obtener_config_centro",
    "guardar_config_centro",
    "validar_acceso_openrouter"
]
