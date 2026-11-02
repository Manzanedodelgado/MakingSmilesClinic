"""Cliente del operador de Jarvis (.91) para la ruta de WhatsApp.

La web recibe el WhatsApp y se lo pasa a Jarvis; Jarvis decide (qwen3.5-clinica en .117) si
contesta directamente o pide datos a esta web por /internal/jarvis/<agente>/... y devuelve el
texto. Enviarlo y guardarlo en la conversación lo sigue haciendo la web. Cualquier fallo se
convierte en LLMError: el llamador lo trata igual que "sin LLM operativo"."""
import logging
import time

import httpx

from domain.config.settings import settings
from infrastructure.external_apis.llm_client import LLMError

logger = logging.getLogger(__name__)

# Con herramientas (consultar la web o un perfil de Hermes) un turno puede tardar.
TIMEOUT = httpx.Timeout(240.0, connect=5.0)


def _post(agente: str, ruta: str, payload: dict) -> dict:
    url = settings.jarvis_operador_url.rstrip("/") + f"/v1/operadores/{agente}/{ruta}"
    try:
        r = httpx.post(url, json=payload,
                       headers={"Authorization": "Bearer " + settings.jarvis_operador_key},
                       timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("jarvis_operador: %s no respondió (%s)", agente, type(exc).__name__)
        raise LLMError(f"Jarvis no respondió: {type(exc).__name__}") from exc
    if not (data.get("respuesta") or "").strip():
        raise LLMError("Jarvis devolvió una respuesta vacía")
    return data


def pedir_respuesta(agente: str, centro_id: int, telefono: str, texto: str) -> str:
    """WhatsApp de un paciente (Alex): devuelve el texto a enviar."""
    data = _post(agente, "whatsapp", {"centro_id": centro_id, "telefono": telefono, "texto": texto})
    return data["respuesta"].strip()


def pedir_chat(agente: str, centro_id: int, texto: str, historial: list[dict]) -> dict:
    """Chat del equipo con Victor o Aura: {respuesta, herramientas, extra}."""
    return _post(agente, "chat", {"centro_id": centro_id, "texto": texto, "historial": historial})


def pedir_entrenamiento(agente: str, centro_id: int, telefono: str, texto: str,
                        historial: list[dict], escenario: dict | None) -> str:
    """Chat de entrenamiento de Config › Agentes IA: mismo operador de Jarvis que contesta de
    verdad, en simulación (las herramientas no tocan datos y no se registra en Honcho)."""
    data = _post(agente, "entrenamiento", {"centro_id": centro_id, "telefono": telefono, "texto": texto,
                                           "historial": historial, "escenario": escenario})
    return data["respuesta"].strip()


# Agentes de la web que contestan a través de su operador de Jarvis (si hay URL).
AGENTES_POR_JARVIS = {"alex", "victor", "aura"}
_modelo_cache: dict = {"valor": None, "hasta": 0.0}


def modelo_jarvis() -> str | None:
    """Modelo con el que piensan los operadores de Jarvis (GET /v1/operadores/motor). Se
    guarda 5 min; si Jarvis no responde en 3 s, None (la ficha no se queda colgada)."""
    if not settings.jarvis_operador_url:
        return None
    if time.monotonic() < _modelo_cache["hasta"]:
        return _modelo_cache["valor"]
    try:
        r = httpx.get(settings.jarvis_operador_url.rstrip("/") + "/v1/operadores/motor",
                      headers={"Authorization": "Bearer " + settings.jarvis_operador_key},
                      timeout=httpx.Timeout(3.0))
        r.raise_for_status()
        valor = (r.json().get("modelo") or "").removesuffix(":latest") or None
    except (httpx.HTTPError, ValueError):
        valor = None
    _modelo_cache.update(valor=valor, hasta=time.monotonic() + (300 if valor else 30))
    return valor
