"""Interfaz abstracta para proveedores LLM.

El sistema debe funcionar con cualquier proveedor que implemente esta interfaz:
- OllamaProvider
- OpenAIProvider  
- AnotherProvider

Ningún componente del agente debe conocer detalles específicos de HTTP/Ollama.
"""
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Optional


class LLMProvider(ABC):
    """Interfaz abstracta para proveedores de LLM."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Nombre del proveedor (ej: 'ollama', 'openai')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Modelo actual configurado."""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """
        Ejecuta una ronda de chat.
        
        Args:
            messages: Lista de mensajes [{role, content}, ...]
            tools: Lista opcional de herramientas disponibles
            temperature: Temperatura de generación
            max_tokens: Límite de tokens
            stream: Si True, devuelve AsyncGenerator
            
        Returns:
            Dict con 'message' conteniendo content y tool_calls
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming de tokens.
        
        Yields:
            Fragmentos de texto
        """
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generación simple a partir de prompt."""
        pass

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """
        Verifica salud del proveedor.
        
        Returns:
            {'status': 'ok'|'error', 'details': {...}}
        """
        pass

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Lista modelos disponibles en el proveedor."""
        pass
