"""Proveedor LLM genérico para APIs compatibles con OpenAI (Groq, OpenRouter, Cerebras).

Un solo LLMProvider parametrizado por nombre/base_url/api_key/modelo — los tres
proveedores de rescate hablan el mismo protocolo, así que no hace falta una
clase por proveedor.
"""
from typing import Any, AsyncGenerator, Optional

from domain.llm.provider import LLMProvider
from infrastructure.external_apis.openai_compat_client import OpenAICompatClient, OpenAICompatError


class OpenAICompatProvider(LLMProvider):
    """Proveedor LLM basado en un endpoint /chat/completions estilo OpenAI."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str):
        if not api_key:
            raise ValueError(f"{name}: falta API key")
        self._name = name
        self._model = model
        self._client = OpenAICompatClient(base_url=base_url, api_key=api_key, model=model)

    @property
    def provider_name(self) -> str:
        return self._name

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
        try:
            return await self._client.chat(
                messages=messages, tools=tools, temperature=temperature, max_tokens=max_tokens, stream=False
            )
        except OpenAICompatError as e:
            raise RuntimeError(f"{self._name} error: {e}") from e

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        try:
            async for chunk in self._client.stream(
                messages=messages, tools=tools, temperature=temperature, max_tokens=max_tokens
            ):
                yield chunk
        except OpenAICompatError as e:
            raise RuntimeError(f"{self._name} stream error: {e}") from e

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
        result = await self.chat(messages=messages, temperature=temperature, max_tokens=max_tokens)
        return result.get("message", {}).get("content", "")

    async def health_check(self) -> dict[str, Any]:
        try:
            await self._client.health_check()
            return {
                "status": "ok",
                "provider": self._name,
                "model": self._model,
                "details": {"reachable": True},
            }
        except OpenAICompatError as e:
            return {
                "status": "error",
                "provider": self._name,
                "model": self._model,
                "details": {"error": str(e)},
            }

    async def list_models(self) -> list[str]:
        return [self._model]
