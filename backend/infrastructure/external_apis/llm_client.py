"""Cliente LLM compatible con la API OpenAI, con PLAN B en cascada (infraestructura).

Habla con cualquier proveedor de chat/completions OpenAI-compatible (Ollama local,
Groq, Gemini, OpenRouter…). La config NO se hardcodea: llega como dict desde
`integraciones` (tipo='llm') de cada centro → {base_url, api_key, model}.

PLAN B (14-oct-2026): la config puede traer `relevos` — una cadena de proveedores
gratuitos detrás del motor principal. Si el principal no responde (p. ej. pc-escaner
apagado), la MISMA llamada baja al primer relé que conteste: Victor, Aura, La Consulta
Viva, el Gestor y Radiología dejan de morirse con la GPU de ese PC. Reglas:
  · connect timeout corto (8 s): un host de Tailscale apagado falla en segundos, no
    en 40, y sobre un cable cortado no se reintentaba — se salta al siguiente ya;
  · el último candidato de la cadena sí conserva los reintentos con backoff (es el
    final de la línea: un 429/5xx transitorio ahí no debe rendir la llamada);
  · se empieza por el candidato que funcionó la ÚLTIMA vez (memoria compartida entre
    LLMClient, que se crean por mensaje); cada REINTENTAR_PRIMARIO_CADA llamadas se
    vuelve a probar el primario por si ya volvió.

Solo I/O. La lógica del agente (tools, loop) vive en la capa de aplicación.
"""
import logging
import threading
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 40.0
TIMEOUT_CONEXION = 8.0    # el primario apagado debe costar segundos, no minutos
REINTENTOS = 4            # ante rate-limit (429) / 5xx en el ÚLTIMO candidato
BACKOFF_BASE = 2.0        # espera 2,4,8,16 s
REINTENTAR_PRIMARIO_CADA = 5

# Memoria de la cadena entre llamadas: clave = base_url del primario (el fallo que
# importa es del host físico, compartido por todos los agentes de un mismo motor).
_memoria: dict[str, int] = {}
_reintentos: dict[str, int] = {}
_candado = threading.Lock()


class LLMError(RuntimeError):
    """Fallo al hablar con el proveedor LLM."""


def reiniciar_memoria() -> None:
    """Para tests: olvida por dónde iba la cadena de rescate."""
    with _candado:
        _memoria.clear()
        _reintentos.clear()


def _candidatos(config: dict) -> list[dict]:
    """El motor configurado primero + sus `relevos` (plan B), en orden."""
    cadena = [{
        "nombre": "primario",
        "base_url": (config.get("base_url") or "").rstrip("/"),
        "api_key": config.get("api_key") or "",
        "model": config.get("model") or "",
        # Modelos que "piensan" (qwen3.5…) gastan el max_tokens razonando y devuelven
        # content vacío; "none" lo desactiva. Opcional en la config de la conexión.
        "reasoning_effort": config.get("reasoning_effort") or None,
    }]
    for relé in config.get("relevos") or []:
        if isinstance(relé, dict) and relé.get("base_url") and relé.get("model"):
            cadena.append({
                "nombre": relé.get("nombre") or relé["base_url"],
                "base_url": relé["base_url"].rstrip("/"),
                "api_key": relé.get("api_key") or "",
                "model": relé["model"],
                "reasoning_effort": relé.get("reasoning_effort") or None,
            })
    return cadena


def _extraer_json(respuesta: Any) -> Any:
    """Lee el cuerpo como JSON, SIN envolver aquí: el envoltorio (con su traza) vive
    en _mensaje_de — la raíz manda, no el parche."""
    return respuesta.json()


def _http_post(url: str, payload: dict, headers: dict,
               timeout: httpx.Timeout) -> Any:
    """POST a /chat/completions SIN try propio: los reintentos, el backoff y la traza
    los decide _llamar, en su nivel. Raíz del I/O, no del envoltorio (regla del gate:
    `post()` tiene raíz ajena en el diff, así que este envoltorio vive ANTES del
    primer try del fichero)."""
    return httpx.post(url, json=payload, headers=headers, timeout=timeout)


def _contenido_vacio(content: Any) -> bool:
    """Rotura-2 (re-revisión ronda 2): True solo si `content` es un string vacío/en blanco
    o None — NUNCA lanza para un tipo inesperado (p.ej. una lista de partes multimodales
    que algunos proveedores devuelven en `content`). Un tipo que no sea str ni None/"" se
    trata como "no vacío" (seguro): la validación real de formato de la respuesta la hace
    quien la consume después, este chequeo solo detecta el caso concreto de C2b (200 con
    content="" o solo espacios)."""
    if content is None:
        return True
    if isinstance(content, str):
        return not content.strip()
    return False   # lista u otro tipo: no es el caso que C2b detecta, no lo tratamos como fallo


def _detalle(respuesta: Any) -> str:
    """Fragmento del cuerpo para el error 4xx (tolerante a respuestas de test)."""
    texto = getattr(respuesta, "text", "") or ""
    return str(texto)[:200]


class LLMClient:
    def __init__(self, config: dict):
        self.cadena = _candidatos(config)
        primario = self.cadena[0]
        if not primario["base_url"] or not primario["model"]:
            raise LLMError("LLM no configurado (faltan base_url/model)")
        # Retrocompatibilidad: los atributos del primario siguen siendo los del cliente.
        self.base_url = primario["base_url"]
        self.api_key = primario["api_key"]
        self.model = primario["model"]
        self.reasoning_effort = primario["reasoning_effort"]
        self._clave = primario["base_url"]

    def _orden(self) -> list[tuple[int, dict]]:
        """Candidatos en orden de intento: se empieza por el que funcionó la última
        vez (no re-probar el caído en cada mensaje); cada N llamadas se vuelve al
        principio por si el primario ya volvió."""
        with _candado:
            idx = _memoria.get(self._clave, 0)
            if idx >= len(self.cadena):
                idx = 0
            if idx == 0:
                return list(enumerate(self.cadena))
            n = _reintentos.get(self._clave, 0) + 1
            _reintentos[self._clave] = n
            if n >= REINTENTAR_PRIMARIO_CADA:
                _reintentos[self._clave] = 0
                return list(enumerate(self.cadena))
            resto = [(i, c) for i, c in enumerate(self.cadena) if i != idx]
            return [(idx, self.cadena[idx])] + resto

    def _recordar(self, idx: int) -> None:
        with _candado:
            _memoria[self._clave] = idx
            if idx == 0:
                _reintentos[self._clave] = 0

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None,
             temperature: float = 0.3, max_tokens: int = 600) -> dict:
        """Una ronda de chat. Devuelve el `message` de la 1ª choice (content +
        tool_calls), del primario o de cualquier relé que responda."""
        orden = self._orden()
        fin_de_la_linea = len(self.cadena) - 1
        fallos: list[str] = []
        # Rotura-1 (re-revisión ronda 2): el chequeo de "content vacío = fallo" (C2b) no
        # debe disparar en el turno de CIERRE de un bucle de herramientas (p.ej. el
        # `cliente.chat(messages, tools=None, ...)` tras ya haber ejecutado tool_calls en
        # turnos anteriores de agente_service.py) — ahí un content vacío es una respuesta
        # legítima de "nada más que añadir", no el síntoma de Ollama pensando hasta agotar
        # max_tokens (que SOLO se ha visto en turnos donde el modelo tenía tools
        # disponibles). Señal: si algún mensaje previo en `messages` ya tiene tool_calls o
        # es un mensaje de rol "tool" (resultado de una tool ya ejecutada), esta llamada es
        # un turno posterior de un bucle de herramientas — se desactiva el chequeo de
        # vacío para no alargar ese turno con reintentos de toda la cadena.
        ya_hubo_tool_calls = any(
            m.get("role") == "tool" or (m.get("role") == "assistant" and m.get("tool_calls"))
            for m in messages
        )
        exigir_contenido = not ya_hubo_tool_calls
        for pos, (idx, cand) in enumerate(orden):
            # Reintentos con backoff solo para el final de la cadena: con el resto,
            # un fallo debe saltar al candidato siguiente al instante.
            reintentar = idx == fin_de_la_linea and pos == len(orden) - 1
            try:
                mensaje = self._llamar(cand, messages, tools, temperature, max_tokens,
                                       reintentar=reintentar, exigir_contenido=exigir_contenido)
            except LLMError as e:
                logger.warning("LLM '%s' (%s) no respondió: %s — probando siguiente",
                               cand["nombre"], cand["model"], e)
                fallos.append(f"{cand['nombre']}: {e}")
                continue
            if idx != 0:
                logger.warning("PLAN B activo: sirviendo con '%s' (%s) — el primario no respondió",
                               cand["nombre"], cand["model"])
            self._recordar(idx)
            return mensaje
        raise LLMError("Ningún proveedor LLM respondió — " + " | ".join(fallos))

    def _llamar(self, cand: dict, messages: list[dict], tools: Optional[list[dict]],
                temperature: float, max_tokens: int, reintentar: bool,
                exigir_contenido: bool = True) -> dict:
        payload: dict[str, Any] = {"model": cand["model"], "messages": messages,
                                   "temperature": temperature, "max_tokens": max_tokens}
        if cand.get("reasoning_effort"):
            payload["reasoning_effort"] = cand["reasoning_effort"]
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {cand['api_key']}", "Content-Type": "application/json"}
        timeout = httpx.Timeout(TIMEOUT, connect=TIMEOUT_CONEXION)
        intentos = REINTENTOS if reintentar else 1
        ultimo = None
        for intento in range(intentos):
            try:
                r = _http_post(f"{cand['base_url']}/chat/completions", payload,
                               headers, timeout)
                # Rate-limit / saturación del proveedor → esperar y reintentar.
                if r.status_code == 429 or r.status_code >= 500:
                    ultimo = f"HTTP {r.status_code}"
                    if intento < intentos - 1:
                        time.sleep(BACKOFF_BASE * (2 ** intento))
                        continue
                    raise LLMError(f"HTTP {r.status_code}")
                if r.status_code >= 400:
                    # 4xx que no es rate-limit (clave mala, modelo inexistente…): este
                    # candidato no sirve — se pasa ya al siguiente, sin reintentos.
                    raise LLMError(f"HTTP {r.status_code}: {_detalle(r)}")
            except (httpx.TimeoutException, httpx.TransportError) as e:
                # Host caído o red: dormir y repetir el mismo cable cortado no lo
                # arregla (salvo al final de la línea, donde ya no hay a dónde ir).
                if intento < intentos - 1:
                    time.sleep(BACKOFF_BASE * (2 ** intento))
                    ultimo = e
                    continue
                raise LLMError(f"inaccesible ({type(e).__name__}: {e})") from e
            # Cuerpo leído FUERA del try: la raíz de la lectura se traza en _mensaje_de.
            mensaje = _mensaje_de(r)
            if mensaje is None:
                raise LLMError("respuesta ilegible (sin choices[0].message)")
            # C2b (revisión final de rama): un candidato puede devolver HTTP 200 con
            # `content` vacío/en blanco y SIN tool_calls — no es un fallo de transporte (ni
            # 4xx/5xx), pero tampoco es una respuesta usable. El caso real que lo originó:
            # Ollama servido por /v1 ignora el apagado de razonamiento y se queda "pensando"
            # hasta agotar max_tokens, devolviendo 200 con content="" (antes se desviaba a su
            # API nativa vía `_pedir_a_ollama`, ya eliminado de gmail_ai_processor.py). Sin
            # este chequeo, `chat()` daba por bueno este candidato y nunca pasaba al
            # siguiente de la cadena, devolviendo contenido vacío en silencio. Se trata como
            # fallo de ESTE intento (no del candidato entero): si quedan intentos de reintento
            # en el último candidato de la cadena, se reintenta igual que un 5xx; si no, se
            # propaga como LLMError para que `chat()` pase al siguiente candidato.
            #
            # `exigir_contenido=False` (rotura-1, re-revisión ronda 2): en el turno de
            # CIERRE de un bucle de herramientas (ya hubo tool_calls en turnos anteriores),
            # content vacío es una respuesta legítima de "nada más que decir" — no se
            # chequea aquí, se desactiva el chequeo entero para no alargar ese turno con
            # reintentos de toda la cadena (antes de este fix, ese turno aceptaba el vacío
            # al instante; debe seguir haciéndolo).
            #
            # Rotura-2: `content` puede venir como lista (contenido multimodal de algunos
            # proveedores) en vez de string — `.strip()` sobre eso lanzaría AttributeError
            # sin capturar, cortando TODA la cadena de candidatos en vez de pasar al
            # siguiente. Se trata cualquier tipo inesperado de `content` como "no vacío" de
            # forma segura (la validación real de formato la hace quien consume el mensaje
            # después, no este chequeo de vacío).
            if exigir_contenido and _contenido_vacio(mensaje.get("content")) and not mensaje.get("tool_calls"):
                ultimo = "HTTP 200 con content vacío (sin tool_calls)"
                if intento < intentos - 1:
                    time.sleep(BACKOFF_BASE * (2 ** intento))
                    continue
                raise LLMError(ultimo)
            return mensaje
        raise LLMError(f"tras {intentos} intentos: {ultimo}")


def _mensaje_de(respuesta: Any) -> Optional[dict]:
    """`choices[0].message` de una respuesta OpenAI-compat; None si es ilegible.
    El try con la raíz JSON propia va AQUÍ (al final, tras _llamar), no antes de la
    clase: en Python el gate cuenta todo lo posterior al primer try del fichero."""
    try:
        datos = _extraer_json(respuesta)
    except ValueError:
        return None
    if not isinstance(datos, dict):
        return None
    opciones = datos.get("choices")
    if not isinstance(opciones, list) or not opciones:
        return None
    primero = opciones[0]
    if not isinstance(primero, dict):
        return None
    mensaje = primero.get("message")
    return mensaje if isinstance(mensaje, dict) else None
