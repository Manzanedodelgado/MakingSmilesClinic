"""Radiología — clasificación por IA de la MODALIDAD de una imagen radiológica.

La taxonomía es cerrada (el catálogo clínico manda, no el texto libre del modelo). La clasificación
es BEST-EFFORT: si no hay LLM de visión configurado, o el modelo falla/responde algo fuera de la
taxonomía, se devuelve ("sin_clasificar", None) y el doctor corrige a mano. Nunca se inventa.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Optional

from sqlmodel import Session

from application.services.llm_config import resolver_llm
from infrastructure.external_apis.llm_client import LLMClient, LLMError

logger = logging.getLogger("membrana.radiologia")

# Taxonomía cerrada de modalidades radiológicas (código → etiqueta legible).
MODALIDADES: dict[str, str] = {
    "panoramica": "Panorámica (ortopantomografía)",
    "lateral_cefalica": "Telerradiografía lateral de cráneo",
    "periapical": "Periapical",
    "aleta_mordida": "Aleta de mordida",
    "oclusal": "Oclusal",
    "cbct": "CBCT / TAC (3D)",
    "frontal_pa": "Frontal posteroanterior",
    "otra": "Otra",
    "sin_clasificar": "Sin clasificar",
}

_PROMPT = (
    "Eres un asistente de radiología dental. Clasifica la MODALIDAD de esta imagen radiológica "
    "en EXACTAMENTE una de estas claves: panoramica, lateral_cefalica, periapical, aleta_mordida, "
    "oclusal, cbct, frontal_pa, otra. "
    "Responde SOLO un JSON: {\"modalidad\": \"<clave>\", \"confianza\": <0..1>}. "
    "Si no estás seguro, usa \"otra\" con confianza baja. No añadas texto fuera del JSON."
)


def clasificar_modalidad(session: Session, centro_id: int, contenido: bytes,
                         mime: str) -> tuple[str, Optional[float]]:
    """Devuelve (modalidad, confianza). Nunca lanza: ante cualquier fallo → ('sin_clasificar', None)."""
    cfg = resolver_llm(session, centro_id, "victor")  # agente clínico "capaz"; cae a compartido
    if not cfg:
        return "sin_clasificar", None
    try:
        cli = LLMClient(cfg)
        b64 = base64.b64encode(contenido).decode()
        data_uri = f"data:{mime};base64,{b64}"
        messages = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_uri}},
            {"type": "text", "text": _PROMPT},
        ]}]
        msg = cli.chat(messages, max_tokens=120, temperature=0)
        modalidad, confianza = _parsear(msg)
        if modalidad not in MODALIDADES or modalidad == "sin_clasificar":
            return "otra", confianza
        return modalidad, confianza
    except (LLMError, Exception) as e:  # raiz: LLM de visión caído o respuesta inválida, best-effort
        logger.warning("Clasificación de RX no disponible: %s", e)
        return "sin_clasificar", None


def _parsear(msg: dict) -> tuple[str, Optional[float]]:
    """Extrae {modalidad, confianza} del `content` del `message` del modelo (tolera fences y prosa)."""
    content = msg.get("content") if isinstance(msg, dict) else None
    if content is None:
        return "sin_clasificar", None
    if isinstance(content, list):  # algunos modelos devuelven bloques
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    txt = str(content).strip()
    ini, fin = txt.find("{"), txt.rfind("}")
    if ini == -1 or fin == -1:
        return "sin_clasificar", None
    try:
        obj = json.loads(txt[ini:fin + 1])
    except json.JSONDecodeError:
        return "sin_clasificar", None
    modalidad = str(obj.get("modalidad", "")).strip().lower()
    conf = obj.get("confianza")
    try:
        conf = float(conf) if conf is not None else None
        if conf is not None:
            conf = max(0.0, min(1.0, conf))
    except (TypeError, ValueError):
        conf = None
    return modalidad, conf
