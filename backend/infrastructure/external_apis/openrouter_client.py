"""OpenRouter — acceso a Claude 3.5 Sonnet (gratis con fallback)."""
import json
import os
from typing import Any, Dict

import httpx

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "sk-or-v1-demo")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def generar_diagnostico_llm(mediciones: Dict[str, float], notas: str = None) -> Dict[str, Any]:
    """
    Genera diagnóstico ortodóntico usando Claude 3.5 Sonnet vía OpenRouter.
    Retorna: {diagnostico, clase (I/II/III), patron (hipodivergente/normohipso/hiperdivergente)}
    """

    prompt = f"""Eres un ortodoncista experto. Analiza estas mediciones cefalométricas y genera un diagnóstico.

Mediciones:
{json.dumps(mediciones, indent=2)}

Notas clínicas adicionales:
{notas or "Ninguna"}

Responde SOLO en JSON (sin markdown, sin explicaciones) con esta estructura:
{{
  "diagnostico": "Texto del diagnóstico clínico (2-3 oraciones)",
  "clase": "I, II o III",
  "patron": "hipodivergente, normohipso o hiperdivergente"
}}

NO añadas nada más, SOLO el JSON."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://makingsmiles.local",
                    "X-Title": "MakingSmiles Diagnóstico",
                },
                json={
                    "model": "openrouter/auto",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 300,
                },
            )

            if response.status_code != 200:
                raise Exception(f"OpenRouter error {response.status_code}: {response.text}")

            resultado = response.json()
            contenido = resultado["choices"][0]["message"]["content"].strip()

            # Parsear JSON
            diagnostico_json = json.loads(contenido)
            return {
                "diagnostico": diagnostico_json.get("diagnostico", ""),
                "clase": diagnostico_json.get("clase", "I"),
                "patron": diagnostico_json.get("patron", "normohipso"),
            }

    except Exception as e:  # raiz: OpenRouter caído -> fallback sin diagnóstico automático
        # Fallback si OpenRouter falla
        return {
            "diagnostico": f"Diagnóstico automático no disponible: {str(e)}",
            "clase": "I",
            "patron": "normohipso",
        }
