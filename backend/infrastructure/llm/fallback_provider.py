"""Rescate en cascada entre proveedores LLM.

Por qué existe: el proveedor local (Ollama) depende de que una máquina física esté
encendida y alcanzable (verificado 20-sep-2026 — no siempre lo está). En vez de que
cualquier fallo ahí tumbe el chat de Aura, se prueba cada proveedor de la lista en
orden y se usa el primero que responda. Los agentes y el /health no necesitan saber
que existe el fallback: por fuera es un LLMProvider más.
"""
import logging
from typing import Any, AsyncGenerator, Optional

from domain.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


class FallbackProvider(LLMProvider):
    """Prueba una lista de LLMProvider en orden; usa el primero que funcione."""

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("FallbackProvider necesita al menos un proveedor")
        self._providers = providers
        # Recordado entre llamadas: si el primario falló la última vez, no hace
        # falta re-probarlo (y esperar su timeout) en cada mensaje del chat — se
        # reintenta solo, cada N llamadas, por si ya volvió a estar disponible.
        self._ultimo_usado_idx = 0
        self._llamadas_desde_ultimo_exito_primario = 0
        self._REINTENTAR_PRIMARIO_CADA = 5

    @property
    def provider_name(self) -> str:
        return self._providers[self._ultimo_usado_idx].provider_name

    @property
    def model_name(self) -> str:
        return self._providers[self._ultimo_usado_idx].model_name

    def _orden_de_intento(self) -> list[int]:
        """Normalmente empieza por donde se quedó (evita re-probar un caído en cada
        mensaje); cada N llamadas vuelve a intentar desde el primario."""
        if self._ultimo_usado_idx == 0:
            return list(range(len(self._providers)))
        self._llamadas_desde_ultimo_exito_primario += 1
        if self._llamadas_desde_ultimo_exito_primario >= self._REINTENTAR_PRIMARIO_CADA:
            self._llamadas_desde_ultimo_exito_primario = 0
            return list(range(len(self._providers)))
        resto = [i for i in range(len(self._providers)) if i != self._ultimo_usado_idx]
        return [self._ultimo_usado_idx] + resto

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        ultimo_error: Exception | None = None
        for idx in self._orden_de_intento():
            provider = self._providers[idx]
            try:
                resultado = await provider.chat(
                    messages=messages, tools=tools, temperature=temperature, max_tokens=max_tokens, stream=stream
                )
                if idx != self._ultimo_usado_idx:
                    logger.warning(
                        "FallbackProvider: cambiando a '%s' (idx %d), '%s' no respondió",
                        provider.provider_name, idx, self._providers[self._ultimo_usado_idx].provider_name,
                    )
                self._ultimo_usado_idx = idx
                return resultado
            except Exception as e:  # raiz: proveedor caido, se prueba el siguiente
                logger.warning("FallbackProvider: '%s' falló: %s", provider.provider_name, e)
                ultimo_error = e
                continue
        raise RuntimeError(f"Todos los proveedores LLM fallaron. Último error: {ultimo_error}")

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        # El streaming ya ha mandado bytes al cliente en cuanto empieza: no se puede
        # cambiar de proveedor a mitad. Se elige ANTES de emitir nada, con un health
        # check rápido, y ese es el que transmite entero.
        ultimo_error: Exception | None = None
        for idx in self._orden_de_intento():
            provider = self._providers[idx]
            try:
                salud = await provider.health_check()
                if salud.get("status") == "error":
                    raise RuntimeError(salud.get("details", {}).get("error", "no disponible"))
                self._ultimo_usado_idx = idx
                async for chunk in provider.stream(
                    messages=messages, tools=tools, temperature=temperature, max_tokens=max_tokens
                ):
                    yield chunk
                return
            except Exception as e:  # raiz: proveedor caido, se prueba el siguiente
                logger.warning("FallbackProvider (stream): '%s' falló: %s", provider.provider_name, e)
                ultimo_error = e
                continue
        raise RuntimeError(f"Todos los proveedores LLM fallaron. Último error: {ultimo_error}")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        resultado = await self.chat(messages=messages, temperature=temperature, max_tokens=max_tokens)
        return resultado.get("message", {}).get("content", "")

    async def health_check(self) -> dict[str, Any]:
        """Informa del primero que responda OK, pero incluye el estado de TODOS —
        así /health deja de mentir "todo bien" cuando el primario está caído y en
        realidad se está sirviendo desde el proveedor de rescate."""
        estados = []
        primero_ok: dict[str, Any] | None = None
        for idx, provider in enumerate(self._providers):
            salud = await provider.health_check()
            estados.append({"provider": provider.provider_name, **salud})
            if primero_ok is None and salud.get("status") == "ok":
                primero_ok = salud
                primero_ok_idx = idx

        if primero_ok is None:
            return {
                "status": "error",
                "provider": self._providers[0].provider_name,
                "model": self._providers[0].model_name,
                "details": {"error": "Ningún proveedor LLM disponible", "cadena": estados},
            }

        usando_rescate = primero_ok_idx != 0
        return {
            "status": "warning" if usando_rescate else "ok",
            "provider": primero_ok["provider"],
            "model": primero_ok["model"],
            "details": {
                **primero_ok.get("details", {}),
                "usando_rescate": usando_rescate,
                "cadena": estados,
            },
        }

    async def list_models(self) -> list[str]:
        return [self._providers[self._ultimo_usado_idx].model_name]
