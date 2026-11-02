"""Sustitución en caliente de modelos de la cadena de rescate LLM.

Por qué existe: cuando Centinela detecta que el modelo configurado para Groq/OpenRouter
falló (p.ej. descatalogado, como pasó hoy con llama-3.3-70b-versatile), la respuesta correcta
no es solo avisar — es probar otros modelos reales de ESE MISMO proveedor y, si alguno
responde, sustituirlo ya para las próximas llamadas. `get_llm_provider()` (ollama_provider.py)
consulta este override ANTES que el valor fijo de settings.py.

Guardado en memoria del proceso, no en BD: cada reinicio del backend vuelve al modelo de
settings.py, y Centinela lo vuelve a comprobar en su siguiente pase (15:00/22:00 o manual) —
así un valor sustituido nunca queda "para siempre" sin que alguien lo revise.
"""
from __future__ import annotations

_overrides: dict[str, str] = {}


def modelo_activo(proveedor: str, por_defecto: str) -> str:
    return _overrides.get(proveedor, por_defecto)


def sustituir(proveedor: str, modelo_nuevo: str) -> None:
    _overrides[proveedor] = modelo_nuevo


def limpiar(proveedor: str) -> None:
    _overrides.pop(proveedor, None)


def estado() -> dict[str, str]:
    return dict(_overrides)
