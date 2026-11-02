"""Máquina de estados conversacional de WhatsApp (dominio puro).

Port de whatsapp.flows.ts de la .37. SIN efectos: detecta la intención de un
mensaje y, según el estado del flujo, devuelve qué responder, el nuevo estado y
la acción a ejecutar (que aplica la capa de aplicación, con sus guards). Así es
100% testeable sin tocar BBDD ni enviar nada.

Flujos soportados:
  · urgencia            → escala al equipo
  · confirmar/cancelar  → acción sobre la próxima cita (guard 1-paciente en el servicio)
  · consultar_cita      → pide nombre, verifica identidad y devuelve próximas citas
  · reservar_cita       → recoge tratamiento y escala (los huecos reales llegarán
                          cuando exista el motor de disponibilidad de agenda)
  · saludo/general      → mensaje de ayuda
"""
import re
import unicodedata
from typing import Any, Optional, TypedDict


# ─────────────────────────── INTENTS ───────────────────────────
KW = {
    "urgencia": ("urgencia", "dolor", "duele", "duelen", "emergencia", "sangrado",
                 "hinchazon", "flemon", "se me ha caido", "accidente", "no aguanto"),
    "cancelar": ("cancelar", "cancela", "anular", "anula", "no puedo ir", "no voy a ir",
                 "no puedo acudir", "no voy a poder"),
    "reservar": ("cita", "reservar", "agendar", "pedir hora", "pedir cita", "quiero hora",
                 "coger cita", "turno"),
    "consultar": ("mi cita", "mis citas", "proxima cita", "cuando es mi", "cuando tengo",
                  "que cita tengo"),
    "handoff": ("hablar con alguien", "hablar con una persona", "eres un bot", "operador",
                "atencion al cliente", "hablar con recepcion"),
    "confirmar": ("si", "sí", "claro", "confirmo", "confirmado", "de acuerdo", "ok",
                  "vale", "perfecto", "alli estare", "alli estaré"),
    "negar": ("no", "nop", "no quiero", "dejalo", "no gracias", "mejor no"),
}


# Descripción de cada flujo REAL (la lee Motion › Flujos; vive junto al código que describe).
FLUJOS_INFO: list[dict] = [
    {"id": "urgencia", "nombre": "Urgencia / Dolor",
     "detonante": "Palabras clave: " + ", ".join(KW["urgencia"][:6]) + "…",
     "pasos": ["Detectar urgencia en el mensaje", "Escalar al equipo (acción `escalar`)",
               "Responder al paciente con protocolo de urgencia", "Cortar cualquier flujo en curso"]},
    {"id": "confirmar", "nombre": "Confirmación SÍ/NO",
     "detonante": "Respuesta a recordatorio: sí, confirmo, ok, vale…",
     "pasos": ["Detectar intención de confirmar", "Confirmar la próxima cita (estado + confirmada)",
               "Enviar consentimiento COEM si el tipo de cita lo requiere", "Acusar al paciente"]},
    {"id": "cancelar", "nombre": "Cancelación",
     "detonante": "Palabras clave: cancelar, anular, no puedo ir…",
     "pasos": ["Detectar intención de cancelar", "Cancelar la próxima cita (estado cancelada)",
               "Confirmar la cancelación al paciente", "Motion ofrece reprogramar (anulacion_reprogramar)"]},
    {"id": "consultar", "nombre": "Consulta de cita",
     "detonante": "Palabras clave: mi cita, próxima cita, cuándo tengo…",
     "pasos": ["Pedir nombre y apellidos", "Verificar identidad contra la ficha",
               "Devolver las próximas citas", "Ofrecer opciones"]},
    {"id": "reservar", "nombre": "Reservar cita",
     "detonante": "Palabras clave: cita, reservar, pedir hora…",
     "pasos": ["Preguntar el tratamiento", "Recoger la petición",
               "Escalar al equipo para dar hueco", "(Huecos automáticos al llegar el motor de disponibilidad)"]},
    {"id": "general", "nombre": "Conversación general (Alex)",
     "detonante": "Cualquier mensaje que no encaje en otro flujo",
     "pasos": ["Cargar contexto del paciente", "Cargar historial de la conversación",
               "Responder con el agente Alex (LLM)", "Detectar escalación implícita / handoff"]},
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Puntuación → espacio para que el match por límites no se rompa con ¿? , . etc.
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def detectar_intent(texto: str) -> str:
    """Primer intent que casa por palabra/expresión (orden = prioridad)."""
    low = f" {_norm(texto)} "
    for intent in ("urgencia", "cancelar", "consultar", "reservar", "handoff", "confirmar", "negar"):
        for kw in KW[intent]:
            if f" {kw} " in low or low.strip() == kw or low.strip().startswith(kw + " "):
                return intent
    return "general"


# ─────────────────────────── TIPOS ───────────────────────────
class Resultado(TypedDict, total=False):
    respuesta: str
    nuevo_estado: Optional[dict]
    accion: Optional[dict]          # {"tipo": "confirmar"|"cancelar"|"escalar"|"citas", ...}


def _r(respuesta: str, nuevo_estado: Optional[dict] = None,
       accion: Optional[dict] = None) -> Resultado:
    return {"respuesta": respuesta, "nuevo_estado": nuevo_estado, "accion": accion}


# ─────────────────────────── IDENTIDAD (más estricta que la .37) ───────────────────────────
def verificar_identidad(nombre_dado: str, nombres_ficha: list[str]) -> bool:
    """Verdadero solo si el nombre dado comparte >=2 tokens con alguna ficha (o es igual).
    Evita el bug .37 de validar con un solo nombre de pila por substring."""
    dado = set(_norm(nombre_dado).split())
    if not dado:
        return False
    for ficha in nombres_ficha:
        toks = set(_norm(ficha).split())
        if not toks:
            continue
        if dado == toks:
            return True
        if len(dado & toks) >= 2:
            return True
    return False


# ─────────────────────────── FLUJOS ───────────────────────────
def manejar(estado: Optional[dict], texto: str, ctx: dict) -> Resultado:
    """Punto de entrada. `estado` = flujo en curso (o None). `ctx` aporta datos del
    paciente que el flujo necesita: {nombres: [...], tiene_paciente: bool, n_pacientes}."""
    estado = estado or {}
    paso = estado.get("paso")
    intent_actual = estado.get("intent")
    intent = detectar_intent(texto)

    # Cancelar/urgencia/handoff cortan cualquier flujo en curso.
    if intent == "urgencia":
        return _r("He avisado al equipo de tu urgencia; te atenderemos con prioridad. "
                  "Si es grave, llama directamente a la clínica.",
                  nuevo_estado=None, accion={"tipo": "escalar", "motivo": "urgencia"})
    if intent == "handoff":
        return _r("Te paso con una persona del equipo. En breve te responden.",
                  nuevo_estado=None, accion={"tipo": "escalar", "motivo": "solicita_humano"})

    # Continuación de un flujo multipaso
    if intent_actual == "consultar" and paso == "verificar":
        return _flujo_consultar_verificar(texto, ctx)
    if intent_actual == "reservar" and paso == "tratamiento":
        return _flujo_reservar_tratamiento(texto)

    # Nuevos intents
    if intent == "confirmar":
        return _r("¡Perfecto! Doy tu cita por confirmada. ¡Nos vemos!",
                  nuevo_estado=None, accion={"tipo": "confirmar"})
    if intent == "cancelar":
        return _r("Entendido, gestiono la cancelación de tu próxima cita.",
                  nuevo_estado=None, accion={"tipo": "cancelar"})
    if intent == "consultar":
        return _r("Para consultar tus citas necesito verificar tu identidad. "
                  "¿Me dices tu nombre y apellidos, por favor?",
                  nuevo_estado={"intent": "consultar", "paso": "verificar"})
    if intent == "reservar":
        return _r("¡Claro! ¿Para qué tratamiento necesitas la cita? "
                  "(revisión, limpieza, ortodoncia, implante…)",
                  nuevo_estado={"intent": "reservar", "paso": "tratamiento"})

    # Saludo / general
    return _r("Hola 👋 Soy el asistente de la clínica. Puedo ayudarte a confirmar o "
              "cancelar una cita, consultar tus próximas citas o pedir una nueva. "
              "¿Qué necesitas?", nuevo_estado=None)


def _flujo_consultar_verificar(texto: str, ctx: dict) -> Resultado:
    if not ctx.get("tiene_paciente"):
        return _r("No encuentro una ficha asociada a este número. Te paso con el equipo.",
                  nuevo_estado=None, accion={"tipo": "escalar", "motivo": "sin_ficha"})
    if not verificar_identidad(texto, ctx.get("nombres", [])):
        return _r("Por seguridad no puedo confirmar tu identidad por aquí. "
                  "Le paso el mensaje al equipo para que te atienda.",
                  nuevo_estado=None, accion={"tipo": "escalar", "motivo": "identidad_no_verificada"})
    return _r("", nuevo_estado=None, accion={"tipo": "citas"})  # el servicio rellena la respuesta


def _flujo_reservar_tratamiento(texto: str) -> Resultado:
    tratamiento = (texto or "").strip()[:120] or "una valoración"
    return _r(f"Perfecto, anoto que quieres cita para «{tratamiento}». "
              "El equipo te confirmará el primer hueco disponible en breve.",
              nuevo_estado=None,
              accion={"tipo": "escalar", "motivo": "solicitud_cita", "detalle": tratamiento})
