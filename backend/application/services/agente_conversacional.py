"""Motor de conversación compartido por los agentes IA que hablan por chat (Victor, Aura).

Antes VictorAgente y AuraAgente tenían cada uno su propio bucle de tool-calling — idéntico
en estructura (mismo límite de iteraciones, misma construcción de mensajes, mismo manejo de
errores del LLM) y solo distinto en el prompt, las herramientas y el despacho. Duplicar esa
forma es exactamente el sitio donde un arreglo futuro (p. ej. cómo se recupera una tool_call
mal formada) se aplica a uno y se olvida en el otro — es lo que pasó con el rescate de
tool_call-en-texto, que Aura tenía y Victor no, sin que hubiera un motivo real para la
diferencia. Aquí se factoriza una sola vez; cada agente aporta su prompt, sus herramientas y
su despacho.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlmodel import Session

from application.services.llm_config import resolver_llm
from infrastructure.external_apis.llm_client import LLMClient, LLMError

MAX_ITERS = 6


def tool_call_en_texto(contenido: str) -> Optional[dict]:
    """Salvaguarda: algunos modelos locales (ver domain/config/agentes.py — "falla la
    mitad") a veces escriben la llamada a herramienta como JSON dentro de `content` en vez
    de usar el campo `tool_calls` de la API. Si el texto es exactamente eso, se recupera en
    vez de tratarlo como la respuesta final al usuario."""
    if not contenido:
        return None
    crudo = contenido.strip()
    if "```" in crudo:
        partes = crudo.split("```")
        if len(partes) >= 2:
            crudo = partes[1].removeprefix("json").strip()
    try:
        d = json.loads(crudo)
    except json.JSONDecodeError:
        return None
    if isinstance(d, dict) and "name" in d and isinstance(d.get("arguments", {}), dict):
        return {"id": "fallback-0",
                "function": {"name": d["name"], "arguments": json.dumps(d.get("arguments", {}))}}
    return None


class AgenteConversacional:
    """Un turno de chat con herramientas. Cada agente define quién es (`agente_id`), cómo
    habla (`system`/`herramientas`) y qué hace cada herramienta (`ejecutar`); este bucle es
    igual para todos: llama al LLM, despacha las tool_calls que pida, repite hasta que
    conteste en texto o se agoten los intentos.

    `recupera_tool_call_en_texto`: activarlo para modelos que a veces devuelven la llamada
    como JSON suelto en vez de `tool_calls` (ver `tool_call_en_texto` arriba)."""

    agente_id: str
    recupera_tool_call_en_texto: bool = False
    # Agentes cuyas cifras salen SOLO de herramientas: sin consulta, una respuesta con importes se descarta.
    exige_consulta = False

    def respuesta_sin_consultar(self, texto: str) -> bool:
        return False

    def __init__(self, session: Session, centro_id: int):
        self.s = session
        self.centro_id = centro_id

    # Clave de CONFIG donde vive `persona` (Config → Agentes IA → espacio del agente).
    # Cada subclase la fija: "agente.victor" o "aura.config".
    config_key: str = ""
    config_sistema: str = "ia"

    def _persona_extra(self) -> str:
        """Trato/idioma configurados en Config → Agentes IA (ver EntrenamientoAgente.tsx).
        Mismo bug que tuvo Alex antes de arreglarse: los campos se guardaban pero nadie los
        leía al construir el prompt — aquí si entran de verdad."""
        if not self.config_key:
            return ""
        from application.services.config_service import ConfigService
        cfg = ConfigService(self.s).resolve(self.config_key, centro_id=self.centro_id,
                                            sistema=self.config_sistema, default=None)
        p = (cfg or {}).get("persona") if isinstance(cfg, dict) else None
        if not isinstance(p, dict):
            return ""
        lineas: list[str] = []
        if isinstance(p.get("nombre"), str) and p["nombre"].strip():
            lineas.append(f"Te llamas {p['nombre'].strip()}.")
        idioma = p.get("idioma") if isinstance(p.get("idioma"), str) else ""
        if idioma and idioma != "es":
            NOMBRES_IDIOMA = {"en": "inglés", "fr": "francés", "de": "alemán", "ca": "catalán"}
            lineas.append(f"Responde SIEMPRE en {NOMBRES_IDIOMA.get(idioma, idioma)}.")
        if isinstance(p.get("tono"), str) and p["tono"].strip():
            lineas.append(p["tono"].strip())

        def _nivel(v, bajo, alto):
            try:
                v = int(v)
            except (TypeError, ValueError):
                return None
            return alto if v >= 4 else (bajo if v <= 1 else None)

        lineas += [x for x in (
            _nivel(p.get("cercania"), "Mantén un tono neutro y sobrio.", "Sé cercano y cálido en el trato."),
            _nivel(p.get("proactividad"), "No te adelantes: responde a lo que pregunten, sin ofrecer de más.", "Anticípate y ofrece ayuda proactivamente cuando encaje."),
            _nivel(p.get("formalidad"), "Usa un registro relajado.", "Usa un registro formal y cuidado."),
        ) if x]
        if isinstance(p.get("bienvenida"), str) and p["bienvenida"].strip():
            lineas.append(f"Al empezar una conversación nueva, saluda en la línea de: «{p['bienvenida'].strip()}».")
        if isinstance(p.get("despedida"), str) and p["despedida"].strip():
            lineas.append(f"Al cerrar, despídete en la línea de: «{p['despedida'].strip()}».")
        if not lineas:
            return ""
        return "\n\nTRATO, IDIOMA Y PERSONALIDAD (configurado por la clínica):\n" + "\n".join(lineas)

    # Las subclases implementan estos tres puntos de extensión:
    def system(self) -> str:
        raise NotImplementedError

    def herramientas(self) -> list[dict]:
        raise NotImplementedError

    def ejecutar(self, nombre: str, args: dict) -> str:
        """Debe devolver JSON (string) — nunca lanzar: un error de herramienta vuelve al
        LLM como resultado, no tumba la conversación."""
        raise NotImplementedError

    def extra(self) -> dict:
        """Claves adicionales que un agente concreto quiera añadir a la respuesta final
        (p.ej. Victor añade `accionesPendientes`). Vacío por defecto."""
        return {}

    def responder(self, texto: str, *, historial: Optional[list[dict]] = None,
                  llm: Optional[LLMClient] = None) -> dict:
        from domain.config.settings import settings
        from infrastructure.external_apis.jarvis_operador import AGENTES_POR_JARVIS
        # Solo los agentes con operador en Jarvis (Alex, Victor, Aura). El Gestor no tiene: iba a
        # Jarvis igualmente y recibía 404 "Sin operador de chat para gestor" (29-oct-2026).
        if settings.jarvis_operador_url and llm is None and self.agente_id in AGENTES_POR_JARVIS:
            # Por Jarvis: su operador piensa y ejecuta estas mismas herramientas en la web
            # (/internal/jarvis/<agente>/herramienta); aquí solo se devuelve su respuesta.
            from infrastructure.external_apis.jarvis_operador import pedir_chat
            try:
                r = pedir_chat(self.agente_id, self.centro_id, texto or "", historial or [])
            except LLMError as e:
                return {"ok": False, "respuesta": f"El modelo no respondió: {e}"}
            respuesta = r.get("respuesta") or "¿En qué te ayudo?"
            return {"ok": True, "respuesta": respuesta,
                    "herramientasUsadas": r.get("herramientas") or [],
                    "historial": (historial or []) + [
                        {"role": "user", "content": texto or ""},
                        {"role": "assistant", "content": respuesta}],
                    **(r.get("extra") or {})}
        cfg = resolver_llm(self.s, self.centro_id, self.agente_id)
        if not cfg:
            return {"ok": False, "respuesta": f"{self.agente_id.capitalize()} no tiene modelo de IA configurado."}
        cliente = llm or LLMClient(cfg)

        messages: list[dict] = [{"role": "system", "content": self.system() + self._persona_extra()}]
        messages.extend(historial or [])
        messages.append({"role": "user", "content": texto or ""})

        tools = self.herramientas()
        usadas: list[str] = []
        respuesta = ""
        reintentos_sin_consulta = 0
        for _ in range(MAX_ITERS + 2):
            try:
                msg = cliente.chat(messages, tools, max_tokens=700)
            except LLMError as e:
                return {"ok": False, "respuesta": f"El modelo no respondió: {e}"}
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls and self.recupera_tool_call_en_texto:
                rescatada = tool_call_en_texto(msg.get("content") or "")
                if rescatada:
                    tool_calls = [rescatada]
                    msg = {**msg, "content": None, "tool_calls": tool_calls}
            if not tool_calls:
                respuesta = msg.get("content") or ""
                if self.exige_consulta and not usadas and self.respuesta_sin_consultar(respuesta):
                    if reintentos_sin_consulta < 2:
                        reintentos_sin_consulta += 1
                        messages.append(msg)
                        messages.append({"role": "user", "content": (
                            "SISTEMA: has dado cifras o 'consultando' sin llamar a ninguna herramienta. "
                            "Llama AHORA a las herramientas y responde solo con lo que devuelvan.")})
                        continue
                    respuesta = ("No he conseguido consultar el informe contable en este intento. "
                                 "Vuelve a preguntármelo, por favor.")
                break
            messages.append(msg)
            for tc in tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                nombre = fn.get("name", "")
                usadas.append(nombre)
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                 "content": self.ejecutar(nombre, args)})

        return {"ok": True, "respuesta": respuesta or "¿En qué te ayudo?",
                "herramientasUsadas": usadas,
                "historial": (historial or []) + [
                    {"role": "user", "content": texto or ""},
                    {"role": "assistant", "content": respuesta}],
                **self.extra()}
