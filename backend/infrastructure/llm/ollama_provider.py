"""Proveedor LLM para Ollama.

Implementa LLMProvider usando OllamaClient.
"""
from typing import Any, AsyncGenerator, Optional

from domain.llm.provider import LLMProvider
from domain.config.settings import settings
from infrastructure.external_apis.ollama_client import OllamaClient, OllamaError


class OllamaProvider(LLMProvider):
    """Proveedor LLM basado en Ollama."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        # Configuración desde variables de entorno
        self._base_url = base_url or getattr(settings, "llm_base_url", None)
        self._model = model or getattr(settings, "llm_model", "qwen2.5-coder:7b")
        
        if not self._base_url:
            raise ValueError(
                "LLM_BASE_URL no configurado. "
                "Define LLM_BASE_URL en variables de entorno."
            )
        
        self._client = OllamaClient(
            base_url=self._base_url,
            model=self._model
        )

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Ejecuta chat con Ollama."""
        try:
            result = await self._client.chat(
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False
            )
            return result
        except OllamaError as e:
            raise RuntimeError(f"OllamaProvider error: {e}") from e

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming de chat."""
        try:
            async for chunk in self._client.stream(
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens
            ):
                yield chunk
        except OllamaError as e:
            raise RuntimeError(f"OllamaProvider stream error: {e}") from e

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generación simple."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        result = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return result.get("message", {}).get("content", "")

    async def health_check(self) -> dict[str, Any]:
        """Verifica salud de Ollama."""
        try:
            await self._client.health_check()
            model_exists = await self._client.model_exists()
            
            return {
                "status": "ok" if model_exists else "warning",
                "provider": self.provider_name,
                "model": self.model_name,
                "details": {
                    "ollama_reachable": True,
                    "model_available": model_exists,
                    "base_url": self._base_url
                }
            }
        except OllamaError as e:
            return {
                "status": "error",
                "provider": self.provider_name,
                "model": self.model_name,
                "details": {
                    "error": str(e),
                    "base_url": self._base_url
                }
            }

    async def list_models(self) -> list[str]:
        """Lista modelos disponibles."""
        try:
            return await self._client.list_models()
        except OllamaError:
            return []


def _firma_configuracion() -> tuple:
    """Huellas de lo que define la cadena: settings + sustituciones en caliente de
    Centinela. Si alguna cambia, se reconstruye el proveedor; si no, se reutiliza
    con su memoria de rescate intacta."""
    from infrastructure.llm.rescate_override import estado
    return (
        settings.llm_base_url, settings.llm_model,
        settings.groq_api_key, settings.groq_model,
        settings.gemini_api_key_free, settings.gemini_model_free,
        settings.openrouter_api_key, settings.openrouter_model,
        settings.rescate_nube_que_entrena,
        tuple(sorted(estado().items())),
    )


# Caché del proveedor. SIN ella, cada mensaje crea un FallbackProvider nuevo con la
# memoria de rescate a cero: con el motor local caído, CADA mensaje volvería a pagar
# el timeout de conexión al PC apagado (hasta 40 s) antes de bajar a la nube. Con ella,
# el primario se salta tras el primer fallo y se reintenta solo cada N llamadas.
_PROVEEDOR: Optional[LLMProvider] = None
_FIRMA: tuple = ()


def reiniciar_proveedor_llm() -> None:
    """Para tests: obliga a reconstruir el proveedor (y olvida el rescate en marcha)."""
    global _PROVEEDOR, _FIRMA
    _PROVEEDOR = None
    _FIRMA = ()


def get_llm_provider() -> LLMProvider:
    """
    Factory para obtener proveedor LLM según configuración (con memoria entre
    llamadas — ver la caché de arriba).

    Devuelve SIEMPRE un FallbackProvider: Ollama (local, primario) seguido de los
    proveedores gratuitos en la nube que tengan API key configurada (Groq, Gemini,
    OpenRouter — en ese orden; modelos verificados con llamada real el 14-oct-2026).
    Si Ollama no está operativo (depende de una máquina que puede estar apagada),
    el chat sigue funcionando con el primero de rescate que responda, sin que el
    agente ni el /health tengan que saber que ha cambiado de proveedor.
    """
    global _PROVEEDOR, _FIRMA
    firma = _firma_configuracion()
    if _PROVEEDOR is not None and _FIRMA == firma:
        return _PROVEEDOR

    from infrastructure.llm.fallback_provider import FallbackProvider
    from infrastructure.llm.openai_compat_provider import OpenAICompatProvider
    from infrastructure.llm.rescate_override import modelo_activo

    providers: list[LLMProvider] = [OllamaProvider()]

    rescates = [
        ("groq", settings.groq_api_key, settings.groq_base_url, settings.groq_model),
        ("gemini", settings.gemini_api_key_free, settings.gemini_base_url, settings.gemini_model_free),
        ("openrouter", settings.openrouter_api_key, settings.openrouter_base_url, settings.openrouter_model),
    ]
    # Gemini (API gratuita) y los modelos ":free" de OpenRouter pueden usar lo que reciben
    # para entrenar, y a los agentes les llegan datos de pacientes (RGPD, 23-oct-2026).
    # Fuera del rescate salvo que se active a propósito RESCATE_NUBE_QUE_ENTRENA=true.
    if not settings.rescate_nube_que_entrena:
        rescates = [r for r in rescates if r[0] == "groq"]
    for nombre, api_key, base_url, model_default in rescates:
        if api_key:
            # Si Centinela sustituyó el modelo de este proveedor (ver rescate_override.py),
            # se usa el sustituto en vez del fijo de settings.py.
            model = modelo_activo(nombre, model_default)
            providers.append(OpenAICompatProvider(name=nombre, base_url=base_url, api_key=api_key, model=model))

    if len(providers) == 1:
        _PROVEEDOR = providers[0]
    else:
        _PROVEEDOR = FallbackProvider(providers)
    _FIRMA = firma
    return _PROVEEDOR
