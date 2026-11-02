"""Cliente HTTP para APIs compatibles con OpenAI (Groq, OpenRouter, Cerebras, ...).

Los tres proveedores de rescate exponen el mismo formato /chat/completions,
así que un solo cliente parametrizado por base_url/api_key/model basta —
evita triplicar la lógica de reintentos y parsing que ya existe en OllamaClient.
"""
import asyncio
import logging
from typing import Any, AsyncGenerator, Optional

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 30.0
REINTENTOS = 2
BACKOFF_BASE = 1.5


class OpenAICompatError(RuntimeError):
    """Error al comunicarse con un proveedor compatible con OpenAI."""
    pass


class OpenAICompatClient:
    """Cliente HTTP mínimo para /chat/completions estilo OpenAI."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def health_check(self) -> dict[str, Any]:
        """No todos estos proveedores tienen /models público sin coste; un chat de 1
        token es la comprobación más fiable de que la key y el modelo funcionan."""
        try:
            await self.chat(
                messages=[{"role": "user", "content": "ping"}],
                temperature=0.0,
                max_tokens=1,
            )
            return {"status": "ok", "details": {"reachable": True}}
        except Exception as e:  # raiz: cualquier fallo se convierte en OpenAICompatError
            raise OpenAICompatError(f"{self.base_url} no accesible: {e}") from e

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools

        ultimo_error: Exception | None = None
        for intento in range(REINTENTOS):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self._url("/chat/completions"),
                        json=payload,
                        headers=self._headers(),
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        ultimo_error = OpenAICompatError(f"HTTP {response.status_code}: {response.text[:200]}")
                        await asyncio.sleep(BACKOFF_BASE * (2 ** intento))
                        continue

                    response.raise_for_status()
                    data = response.json()
                    choice = (data.get("choices") or [{}])[0]
                    message = choice.get("message", {})

                    return {
                        "message": {
                            "role": message.get("role", "assistant"),
                            "content": message.get("content", ""),
                            "tool_calls": message.get("tool_calls"),
                        },
                        "usage": data.get("usage", {}),
                    }
            except (httpx.TimeoutException, httpx.TransportError) as e:
                ultimo_error = e
                await asyncio.sleep(BACKOFF_BASE * (2 ** intento))
            except httpx.HTTPStatusError as e:
                # 4xx (salvo 429, ya tratado arriba) no se arregla reintentando: key mala,
                # modelo inexistente... fallar rápido para que el fallback pase al siguiente.
                raise OpenAICompatError(f"{self.base_url}: {e.response.status_code} {e.response.text[:200]}") from e

        raise OpenAICompatError(f"Chat falló tras {REINTENTOS} intentos: {ultimo_error}")

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", self._url("/chat/completions"), json=payload, headers=self._headers()
                ) as response:
                    response.raise_for_status()
                    malformadas = 0
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            import json
                            chunk = json.loads(data_str)
                            delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except Exception:  # raiz: chunk corrupto no debe tumbar el stream
                            malformadas += 1
                            if malformadas == 1 or malformadas % 50 == 0:
                                logger.warning("openai-compat: %d chunks malformados en este stream", malformadas)
        except Exception as e:  # raiz: fallo del streaming se convierte en OpenAICompatError
            raise OpenAICompatError(f"Streaming falló: {e}") from e
