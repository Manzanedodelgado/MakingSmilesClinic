"""Cliente HTTP para Ollama API.

Responsable de:
- health check
- listado de modelos
- chat
- streaming
- errores
- timeout
- retry
- conexión

El Agent Orchestrator NO debe conocer detalles específicos de HTTP/Ollama.
"""
import asyncio
import logging
from typing import Any, AsyncGenerator, Optional

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 40.0
REINTENTOS = 4
BACKOFF_BASE = 2.0


class OllamaError(RuntimeError):
    """Error al comunicarse con Ollama."""
    pass


class OllamaClient:
    """Cliente HTTP para Ollama API."""

    def __init__(self, base_url: str, model: str, timeout: float = TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    async def health_check(self) -> dict[str, Any]:
        """Verifica que Ollama esté accesible."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self._url("/api/tags"))
                response.raise_for_status()
                return {"status": "ok", "details": {"reachable": True}}
        except Exception as e:  # raiz: cualquier fallo de conexion a Ollama se convierte en OllamaError
            raise OllamaError(f"Ollama no accesible: {e}") from e

    async def list_models(self) -> list[str]:
        """Lista modelos disponibles."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self._url("/api/tags"))
                response.raise_for_status()
                data = response.json()
                models = [m.get("name") for m in data.get("models", [])]
                return models
        except Exception as e:  # raiz: cualquier fallo de conexion a Ollama se convierte en OllamaError
            raise OllamaError(f"No se pudieron listar modelos: {e}") from e

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """
        Chat con Ollama.
        
        Ollama usa formato diferente a OpenAI. Se adapta aquí.
        """
        # Conversión de mensajes OpenAI -> Ollama
        ollama_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            # Ollama no soporta 'system' como role separado, lo movemos a 'user'
            if role == "system":
                ollama_messages.append({
                    "role": "user",
                    "content": f"[SYSTEM]\n{msg.get('content', '')}"
                })
            else:
                ollama_messages.append({
                    "role": role,
                    "content": msg.get("content", "")
                })

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": ollama_messages,
            # 21-oct-2026: EXPLICITO. Ollama >=0.34 responde en NDJSON (streaming) si
            # falta este campo: response.json() reventaba con "Extra data: line 2" y
            # el FallbackProvider bajaba al plan B (Groq, qwen3.8-27b) con la GPU sana,
            # de forma permanente. Los 4 agentes dejaban de usar qwen3.5-clinica y los
            # datos de pacientes salian a la nube sin que nada lo avisara.
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        # Ollama no soporta tools nativamente en todas las versiones
        # Por ahora, tools se ignoran a nivel de Ollama y se manejan en el provider
        # if tools:
        #     payload["tools"] = tools

        ultimo_error = None
        for intento in range(REINTENTOS):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self._url("/api/chat"),
                        json=payload,
                        timeout=self.timeout
                    )
                    
                    if response.status_code == 429 or response.status_code >= 500:
                        ultimo_error = OllamaError(f"HTTP {response.status_code}")
                        await asyncio.sleep(BACKOFF_BASE * (2 ** intento))
                        continue
                    
                    response.raise_for_status()
                    
                    if stream:
                        # Para streaming, se maneja en stream() separado
                        pass
                    
                    data = response.json()
                    message = data.get("message", {})
                    
                    return {
                        "message": {
                            "role": message.get("role", "assistant"),
                            "content": message.get("content", ""),
                            "tool_calls": None  # Ollama no devuelve tool_calls nativos
                        },
                        "usage": data.get("usage", {})
                    }
                    
            except (httpx.TimeoutException, httpx.TransportError) as e:
                ultimo_error = e
                await asyncio.sleep(BACKOFF_BASE * (2 ** intento))
            except Exception as e:  # raiz: error transitorio de red, se reintenta
                ultimo_error = e
                await asyncio.sleep(BACKOFF_BASE * (2 ** intento))
        
        raise OllamaError(f"Chat falló tras {REINTENTOS} intentos: {ultimo_error}")

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming de chat con Ollama."""
        ollama_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                ollama_messages.append({
                    "role": "user",
                    "content": f"[SYSTEM]\n{msg.get('content', '')}"
                })
            else:
                ollama_messages.append({
                    "role": role,
                    "content": msg.get("content", "")
                })

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    self._url("/api/chat"),
                    json=payload,
                    timeout=self.timeout
                ) as response:
                    response.raise_for_status()
                    
                    malformadas = 0
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = httpx.Response(content=line.encode(), status_code=200).json()
                            message = data.get("message", {})
                            content = message.get("content", "")
                            if content:
                                yield content
                            
                            if data.get("done"):
                                break
                        except Exception:  # raiz: linea corrupta del stream no debe tumbarlo
                            # Ignorar líneas malformadas, pero contarlas: un truncamiento
                            # masivo indica proveedor roto, no ruido.
                            malformadas += 1
                            if malformadas == 1 or malformadas % 50 == 0:
                                logger.warning("ollama: %d chunks malformados en este stream", malformadas)
        except Exception as e:  # raiz: fallo del streaming se convierte en OllamaError
            raise OllamaError(f"Streaming falló: {e}") from e

    async def model_exists(self) -> bool:
        """Verifica si el modelo está disponible."""
        try:
            models = await self.list_models()
            return self.model in models
        except OllamaError:
            return False
