"""Motores de transcripción (voz → texto) para Aura. Implementan el puerto
`domain/interfaces/transcripcion.py`.

Hay DOS y no uno a propósito. Cuando NVIDIA retiró un modelo sin avisar, toda la IA de
texto murió porque había un único proveedor incrustado. Aquí el principal es Groq y el
respaldo es Gemini: si el primero falla (caída, límite de uso, modelo retirado), Aura sigue
escuchando en vez de quedarse muda.

Medido con audio real de consulta dental en español (27,4 s), 24-jul-2026:

    Groq whisper-large-v3-turbo   0,7 s   x38   6/8 términos clínicos
    Groq whisper-large-v3         1,1 s   x26   7/8  ← elegido
    Gemini 2.5-flash              2,5 s   x11   7/8  ← respaldo
    faster-whisper local (4 CPU)  795 s   x0,1  — inviable, descartado

Se eligió `whisper-large-v3` y no el turbo porque en clínica la precisión pesa más que
medio segundo: el turbo perdía la pieza dental ("cuatro seis"), y confundir una pieza en
una historia clínica no es un error cosmético.

AVISO RGPD: los dos motores mandan el audio fuera de la clínica, y la voz de una consulta
es dato de salud (art. 9 RGPD). Por eso el puerto expone `envia_fuera`: Aura lo advierte en
pantalla y queda en la auditoría. Un motor local (sin salida de datos) encajaría aquí sin
tocar nada más que este fichero.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Optional

import httpx

from domain.interfaces.transcripcion import Transcripcion

log = logging.getLogger("aura.stt")
TIMEOUT = 180.0          # una consulta larga puede pesar; el envío manda más que el proceso


class STTError(RuntimeError):
    """No se pudo transcribir."""


class GroqSTT:
    """Whisper alojado en Groq. Motor principal."""

    nombre = "Groq · whisper-large-v3"
    envia_fuera = True

    def __init__(self, config: dict):
        self.base = (config.get("base_url") or "https://api.groq.com/openai/v1").rstrip("/")
        self.key = config.get("api_key") or ""
        self.model = config.get("model") or "whisper-large-v3"
        self.idioma = config.get("idioma") or "es"

    def disponible(self) -> tuple[bool, str]:
        if not self.key:
            return False, "Falta la clave de Groq"
        try:
            r = httpx.get(f"{self.base}/models",
                          headers={"Authorization": f"Bearer {self.key}"}, timeout=15)
            if r.status_code in (401, 403):
                return False, "La clave de Groq no es válida"
            if r.status_code != 200:
                return False, f"Groq respondió {r.status_code}"
            ids = {m.get("id") for m in r.json().get("data", [])}
            return (True, "Operativo") if self.model in ids else (False, f"«{self.model}» ya no existe en Groq")
        except httpx.HTTPError as e:
            return False, f"Sin respuesta de Groq ({type(e).__name__})"

    def transcribir(self, audio: bytes, *, nombre_archivo: str = "consulta.wav",
                    idioma: str = "es", contexto: Optional[str] = None) -> Transcripcion:
        datos = {"model": self.model, "language": idioma or self.idioma,
                 "response_format": "verbose_json"}
        # `prompt` orienta al modelo con vocabulario propio (piezas, tratamientos, apellidos):
        # sube bastante el acierto en jerga clínica, que es donde Whisper más falla.
        if contexto:
            # Groq rechaza (400) prompts de más de 896 caracteres. Se recorta con margen:
            # el límite lo impone el proveedor, no nosotros, y saltarlo tira la petición.
            datos["prompt"] = contexto[:880]
        try:
            r = httpx.post(f"{self.base}/audio/transcriptions",
                           headers={"Authorization": f"Bearer {self.key}"},
                           files={"file": (nombre_archivo, audio, "audio/wav")},
                           data=datos, timeout=TIMEOUT)
            if r.status_code != 200:
                raise STTError(f"Groq {r.status_code}: {r.text[:150]}")
            d = r.json()
        except httpx.HTTPError as e:
            raise STTError(f"Groq no respondió: {e}") from e
        return Transcripcion(
            texto=(d.get("text") or "").strip(),
            idioma=d.get("language") or idioma,
            duracion_seg=float(d.get("duration") or 0),
            motor=self.nombre,
            tramos=[{"inicio": s.get("start"), "fin": s.get("end"), "texto": s.get("text")}
                    for s in (d.get("segments") or [])],
        )


class GeminiSTT:
    """Gemini con audio nativo. Respaldo si Groq no está disponible."""

    nombre = "Gemini 2.5 Flash"
    envia_fuera = True

    def __init__(self, config: dict):
        self.key = config.get("api_key") or ""
        self.model = config.get("model") or "gemini-2.5-flash"
        self.base = "https://generativelanguage.googleapis.com/v1beta"

    def disponible(self) -> tuple[bool, str]:
        if not self.key:
            return False, "Falta la clave de Gemini"
        try:
            r = httpx.get(f"{self.base}/models?key={self.key}", timeout=15)
            if r.status_code != 200:
                return False, f"Gemini respondió {r.status_code}"
            ids = {m.get("name", "").replace("models/", "") for m in r.json().get("models", [])}
            return (True, "Operativo") if self.model in ids else (False, f"«{self.model}» no disponible")
        except httpx.HTTPError as e:
            return False, f"Sin respuesta de Gemini ({type(e).__name__})"

    def transcribir(self, audio: bytes, *, nombre_archivo: str = "consulta.wav",
                    idioma: str = "es", contexto: Optional[str] = None) -> Transcripcion:
        instruccion = "Transcribe literalmente este audio en español. Devuelve SOLO el texto."
        if contexto:
            instruccion += f" Vocabulario que puede aparecer: {contexto[:500]}"
        body = {"contents": [{"parts": [
            {"text": instruccion},
            {"inline_data": {"mime_type": "audio/wav",
                             "data": base64.b64encode(audio).decode()}}]}]}
        try:
            r = httpx.post(f"{self.base}/models/{self.model}:generateContent?key={self.key}",
                           json=body, timeout=TIMEOUT)
            if r.status_code != 200:
                raise STTError(f"Gemini {r.status_code}: {r.text[:150]}")
            d = r.json()
            texto = d["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
            raise STTError(f"Gemini no respondió: {e}") from e
        return Transcripcion(texto=texto, idioma=idioma, motor=self.nombre)


def construir_motor(config: dict):
    """Devuelve el motor que toca según `proveedor`. Config-driven, nunca hardcodeado."""
    prov = (config or {}).get("proveedor", "groq").lower()
    return GeminiSTT(config) if prov == "gemini" else GroqSTT(config)
