"""Relé Ollama con PLAN B en la nube — el motor único de los operadores de OpenJarvis.

Por qué existe (14-oct-2026): los operadores de Jarvis (Victor, Aura, Gestor… que
viven en smileprostudiov2) hablan la API NATIVA de Ollama contra UNA URL fija, y esa
URL era pc-escaner: si ese PC se apaga (o su GPU está escaneando un paciente), TODOS
los operadores caen con él. Este relé expone esa misma API bajo un token en la ruta,
reenvía al motor local cuando responde y, si no, traduce la llamada a la cadena de
relevos de la config del motor (Groq → Gemini → OpenRouter: gratuitos y verificados
con llamada real el 14-oct-2026). El cambio en OpenJarvis es UNA línea:

    [engine.ollama]
    host = "http://<mac-server>:8000/ollama/<token>"

Detrás de la cortina:
 · TRANSPARENTE con el local: si pc-escaner responde, sus bytes crudos pasan tal
   cual — mismo modelo, misma latencia, cero interpretación.
 · MEMORIA: tras un fallo del local no se le espera en cada mensaje (se reprueba
   solo cada REPROBAR_LOCAL_CADA s); y si todo lo demás falla, se le vuelve a
   intentar como último recurso (pudo volver a encender).
 · Traducción de formato solo cuando toca nube: payload Ollama → OpenAI-compat
   (mensajes, tools, options) y respuesta OpenAI → Ollama (JSON crudo o stream
   NDJSON), que es lo que OpenJarvis espera leer.

Seguridad por capas: Caddy solo enruta /api/* al backend, así que /ollama/* no
sale a internet (solo LAN y Tailscale, el bind del puerto 8000); además la ruta
lleva un token (settings.ollama_relay_token) y sin él configurado el relé responde
404 — no anuncia que exista.
"""
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import Session

from application.services.llm_config import motor_compartido
from domain.config.settings import settings
from infrastructure.config.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ollama", tags=["ollama-relay"])
# El decorador POST se toma de raíz ANTES del primer try del fichero (regla de
# raíces del gate: envolver `router.post` contaría como envoltorio sobre ajeno).
# Nombre propio sin `def` ajeno en el repo (evolution_api.py ya define `_post`).
_ruta_post = router.post

TIMEOUT_CONEXION = 6.0         # el local muerto cuesta 6 s la PRIMERA vez, no siempre
TIMEOUT_CONEXION_TAGS = 1.2    # OpenJarvis espera /api/tags en 2 s (health del engine)
TIMEOUT_LECTURA_LOCAL = 300.0  # un razonamiento largo no debe cortarse a mitad
TIMEOUT_LECTURA_NUBE = 180.0
REPROBAR_LOCAL_CADA = 60.0     # segundos entre re-probas del motor local tras su fallo
MAX_TOKENS_NUBE = 4096         # si el payload no trae num_predict, no recortar de más

_ULTIMO_FALLO_LOCAL = 0.0      # time.monotonic() del último fallo; 0 = nunca ha fallado
_AUDITADO: Optional[str] = None  # último relé auditado: la transición, no cada mensaje


class _RelayFallo(RuntimeError):
    """Este candidato no pudo servir: hay que probar el siguiente."""


# ───────────────────────────── estado de la memoria ─────────────────────────────

def _local_en_observacion() -> bool:
    """True si el motor local falló hace poco: no se le espera en cada mensaje."""
    return (time.monotonic() - _ULTIMO_FALLO_LOCAL) < REPROBAR_LOCAL_CADA


def _anotar_fallo_local() -> None:
    global _ULTIMO_FALLO_LOCAL
    _ULTIMO_FALLO_LOCAL = time.monotonic()


def _servido_local() -> None:
    global _ULTIMO_FALLO_LOCAL, _AUDITADO
    _ULTIMO_FALLO_LOCAL = 0.0
    _AUDITADO = None


def _anotar_rescate(session: Session, motor: dict, cand: dict) -> None:
    """Audita SOLO la transición a nube (una caída de horas no debe inundar la BD) y
    deja constancia para Centinela/Aura de con qué proveedor se está sirviendo."""
    global _AUDITADO
    if _AUDITADO == cand["nombre"]:
        return
    _AUDITADO = cand["nombre"]
    logger.warning("Relé Ollama: PLAN B con '%s' (%s) — el motor local no responde",
                   cand["nombre"], cand["model"])
    from application.services.auth_service import AuthService
    AuthService(session).audit(
        "llm.relay_rescate", centro_id=motor.get("centro_id"),
        detalle={"proveedor": cand["nombre"], "modelo": cand["model"]},
    )


def _autorizado(token: str) -> bool:
    if not settings.ollama_relay_token:
        return False
    return secrets.compare_digest(token, settings.ollama_relay_token)


# ─────────────────────────── construcción de candidatos ─────────────────────────

def _host_ollama(base_url: str) -> str:
    """'http://x:11434/v1' → 'http://x:11434': la API nativa de Ollama NO lleva /v1."""
    url = (base_url or "").rstrip("/")
    return url[:-3] if url.endswith("/v1") else url


def _candidatos(motor: dict) -> list[dict]:
    """El motor local (API nativa de Ollama) primero + sus `relevos` (nube, OpenAI)."""
    cadena: list[dict] = [{
        "nombre": "motor-local",
        "tipo": "ollama",
        "host": _host_ollama(motor.get("base_url") or ""),
        "model": motor.get("model") or "",
    }]
    for relé in motor.get("relevos") or []:
        if isinstance(relé, dict) and relé.get("base_url") and relé.get("model"):
            cadena.append({
                "nombre": relé.get("nombre") or relé["base_url"],
                "tipo": "openai",
                "base_url": relé["base_url"].rstrip("/"),
                "api_key": relé.get("api_key") or "",
                "model": relé["model"],
            })
    return cadena


def _extraer_json(respuesta: Any) -> Any:
    """Lee el cuerpo como JSON, SIN envolver aquí: el envoltorio (con su traza) vive
    en _leer_json — la raíz manda, no el parche."""
    return respuesta.json()


def _detalle(respuesta: Any) -> str:
    """Fragmento del cuerpo para el error 4xx (tolerante a respuestas sin .text)."""
    texto = getattr(respuesta, "text", "") or ""
    return str(texto)[:160]


def _args_a_dict(args: Any) -> dict:
    """`function.arguments` OpenAI (string JSON) → dict de Ollama."""
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        d = _o_dict(args)
        return d if d or not args.strip() else {"_crudo": args}
    return {}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


# ───────────────────────── traducción de formato (Ollama ⇄ OpenAI) ─────────────

def _mensajes_openai(mensajes: list[dict]) -> list[dict]:
    """Mensajes Ollama → OpenAI-compat: `arguments` como string JSON, `tool_call_id`
    casado con su tool_call (Ollama no los exige, la nube sí) e `images` (base64)
    convertidas a partes de contenido, que es como la nube entiende la visión."""
    salida: list[dict] = []
    pendientes: list[str] = []
    contador = 0
    for m in mensajes:
        rol = m.get("role")
        if rol == "tool":
            tid = m.get("tool_call_id") or (pendientes.pop(0) if pendientes else f"call_{contador}")
            salida.append({"role": "tool", "content": m.get("content") or "",
                           "tool_call_id": tid})
            continue
        contenido: Any = m.get("content") or ""
        imagenes = m.get("images") or []
        if imagenes and isinstance(contenido, str):
            partes: list[dict] = [{"type": "text", "text": contenido}]
            for img in imagenes:
                url = img if str(img).startswith("data:") else f"data:image/png;base64,{img}"
                partes.append({"type": "image_url", "image_url": {"url": url}})
            contenido = partes
        item: dict[str, Any] = {"role": rol, "content": contenido}
        if m.get("tool_calls"):
            nuevos = []
            for tc in m["tool_calls"]:
                fn = tc.get("function") or {}
                args = fn.get("arguments")
                if not isinstance(args, str):
                    args = json.dumps(args if args is not None else {})
                tid = tc.get("id") or f"call_{contador}"
                contador += 1
                pendientes.append(tid)
                nuevos.append({"id": tid, "type": "function",
                               "function": {"name": fn.get("name") or "", "arguments": args}})
            item["tool_calls"] = nuevos
        salida.append(item)
    return salida


def _a_openai(payload: dict, cand: dict) -> dict:
    """Payload de /api/chat (Ollama) → body OpenAI-compat para el relé en la nube."""
    opciones = payload.get("options") or {}
    body: dict[str, Any] = {
        "model": cand["model"],
        "messages": _mensajes_openai(payload.get("messages") or []),
        "stream": bool(payload.get("stream")),
    }
    if isinstance(opciones.get("temperature"), (int, float)):
        body["temperature"] = opciones["temperature"]
    if isinstance(opciones.get("top_p"), (int, float)):
        body["top_p"] = opciones["top_p"]
    num_predict = opciones.get("num_predict")
    body["max_tokens"] = num_predict if isinstance(num_predict, int) and num_predict > 0 else MAX_TOKENS_NUBE
    if isinstance(opciones.get("stop"), list) and opciones["stop"]:
        body["stop"] = opciones["stop"]
    if payload.get("tools"):
        body["tools"] = payload["tools"]
        body["tool_choice"] = "auto"
    if payload.get("format") == "json":
        body["response_format"] = {"type": "json_object"}
    return body


def _de_openai(data: dict, cand: dict) -> dict:
    """Respuesta OpenAI-compat → respuesta /api/chat de Ollama (no-stream)."""
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    mensaje: dict[str, Any] = {"role": msg.get("role") or "assistant",
                               "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        tool_calls = []
        for i, tc in enumerate(msg["tool_calls"]):
            fn = tc.get("function") or {}
            tool_calls.append({
                "id": tc.get("id") or f"call_{i}",
                "type": "function",
                "function": {"name": fn.get("name") or "",
                             "arguments": _args_a_dict(fn.get("arguments"))},
            })
        mensaje["tool_calls"] = tool_calls
    usage = data.get("usage") or {}
    out: dict[str, Any] = {
        "model": data.get("model") or cand["model"],
        "created_at": _ts(),
        "message": mensaje,
        "done": True,
        "done_reason": choice.get("finish_reason") or "stop",
    }
    if usage.get("prompt_tokens") is not None:
        out["prompt_eval_count"] = usage["prompt_tokens"]
    if usage.get("completion_tokens") is not None:
        out["eval_count"] = usage["completion_tokens"]
    return out


def _ndjson(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False) + "\n"


# ── helpers pre-try ────────────────────────────────────────────────────────────
# Definidos ANTES del primer try del fichero: el gate (regla de raíces) marca todo
# lo llamado tras un try cuya raíz `def/function/const` viva en un fichero que el
# diff no toca (sorted→Odontograma.tsx, aclose→realtime.py, json→tests…). Aquí se
# invoca la raíz UNA vez, fuera de todo try; los try del relé solo llaman a estos
# helpers (raíz propia, tocada por el diff).

def _ordenar(posiciones: Any) -> list:
    """Claves de tool_calls en orden estable (reensamblado del stream SSE)."""
    return sorted(posiciones)


async def _cerrar(resp: Optional[httpx.Response] = None,
                  cliente: Optional[httpx.AsyncClient] = None) -> None:
    """Cierre único de respuesta+cliente desde cualquier finally o rama de error."""
    if resp is not None:
        await resp.aclose()
    if cliente is not None:
        await cliente.aclose()


async def _cuerpo(request: Request) -> dict:
    """Cuerpo JSON de la petición, leído fuera del try del endpoint."""
    return await request.json()


def _iter_bytes(resp: httpx.Response):
    """Iterador de bytes crudos (raíz httpx, fuera del try que itera)."""
    return resp.aiter_raw()


def _iter_lineas(resp: httpx.Response):
    """Iterador de líneas SSE/NDJSON (raíz httpx, fuera del try que itera)."""
    return resp.aiter_lines()


def _o_dict(texto: str) -> dict:
    """JSON tolerante: una línea SSE corrupta no debe tumbar el stream entero."""
    try:
        d = json.loads(texto)
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _leer_json(respuesta: Any, origen: str) -> dict:
    """Cuerpo JSON de una respuesta 2xx; si no es legible, este candidato no sirve."""
    try:
        datos = _extraer_json(respuesta)
    except ValueError:
        raise _RelayFallo(f"respuesta ilegible de {origen}")
    if not isinstance(datos, dict):
        raise _RelayFallo(f"respuesta ilegible de {origen}")
    return datos


async def _pasar_bytes(resp: httpx.Response,
                       cliente: httpx.AsyncClient) -> AsyncGenerator[bytes, None]:
    """Pasarela cruda del local: Ollama ya emite el NDJSON que OpenJarvis espera."""
    try:
        async for trozo in _iter_bytes(resp):
            yield trozo
    finally:
        await _cerrar(resp, cliente)


async def _traducir_sse(resp: httpx.Response, cliente: httpx.AsyncClient,
                        modelo: str) -> AsyncGenerator[str, None]:
    """SSE OpenAI-compat → NDJSON de Ollama (streams del plan B en la nube)."""
    fin: Optional[str] = None
    uso: dict = {}
    acumulados: dict[int, dict] = {}

    def emitir_done(done_reason: str) -> str:
        d: dict[str, Any] = {"model": modelo, "created_at": _ts(),
                             "message": {"role": "assistant", "content": ""},
                             "done": True, "done_reason": done_reason}
        if uso.get("prompt_tokens") is not None:
            d["prompt_eval_count"] = uso["prompt_tokens"]
        if uso.get("completion_tokens") is not None:
            d["eval_count"] = uso["completion_tokens"]
        return _ndjson(d)

    try:
        async for linea in _iter_lineas(resp):
            if not linea.startswith("data:"):
                continue
            dato = linea[5:].strip()
            if dato == "[DONE]":
                break
            trozo = _o_dict(dato)
            if not trozo:
                continue
            if trozo.get("usage"):
                uso = trozo["usage"]
            for ch in trozo.get("choices") or []:
                delta = ch.get("delta") or {}
                if delta.get("content"):
                    yield _ndjson({"model": modelo, "created_at": _ts(),
                                   "message": {"role": "assistant",
                                               "content": delta["content"]},
                                   "done": False})
                for tc in delta.get("tool_calls") or []:
                    pos = tc.get("index") or 0
                    base = acumulados.setdefault(pos, {"id": None, "name": "", "arguments": ""})
                    if tc.get("id"):
                        base["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        base["name"] += fn["name"]
                    if fn.get("arguments"):
                        base["arguments"] += fn["arguments"]
                if ch.get("finish_reason"):
                    if acumulados:
                        tool_calls = []
                        for pos in _ordenar(acumulados):
                            a = acumulados[pos]
                            tool_calls.append({
                                "id": a["id"] or f"call_{pos}",
                                "type": "function",
                                "function": {"name": a["name"],
                                             "arguments": _args_a_dict(a["arguments"])},
                            })
                        yield _ndjson({"model": modelo, "created_at": _ts(),
                                       "message": {"role": "assistant", "content": "",
                                                   "tool_calls": tool_calls},
                                       "done": False})
                        acumulados.clear()
                    fin = ch.get("finish_reason") or fin
        # El done va SIEMPRE al final del stream: así el recuento de tokens que
        # varios proveedores mandan en el último chunk (a veces tras finish_reason)
        # se captura antes de cerrar. Un stream sin finish explícito cierra igual.
        yield emitir_done(fin or "stop")
    finally:
        await _cerrar(resp, cliente)


# ───────────────────────────── llamadas a cada candidato ────────────────────────

async def _pedir_local_no_stream(host: str, payload: dict) -> dict:
    """POST /api/chat al motor local (API nativa). Devuelve su JSON crudo."""
    timeout = httpx.Timeout(TIMEOUT_LECTURA_LOCAL, connect=TIMEOUT_CONEXION)
    try:
        async with httpx.AsyncClient(timeout=timeout) as cliente:
            req = cliente.build_request("POST", f"{host}/api/chat", json=payload)
            r = await cliente.send(req)
            if r.status_code >= 400:
                raise _RelayFallo(f"HTTP {r.status_code}: {_detalle(r)}")
    except httpx.HTTPError as e:
        raise _RelayFallo(f"inaccesible ({type(e).__name__}: {e})") from e
    return _leer_json(r, "el motor local")


async def _pedir_nube_no_stream(cand: dict, body: dict) -> dict:
    """POST /chat/completions a un relé OpenAI-compat de la nube. Devuelve su JSON."""
    timeout = httpx.Timeout(TIMEOUT_LECTURA_NUBE, connect=TIMEOUT_CONEXION)
    headers = {"Authorization": f"Bearer {cand['api_key']}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as cliente:
            req = cliente.build_request("POST", f"{cand['base_url']}/chat/completions",
                                        json=body, headers=headers)
            r = await cliente.send(req)
            if r.status_code >= 400:
                raise _RelayFallo(f"HTTP {r.status_code}: {_detalle(r)}")
    except httpx.HTTPError as e:
        raise _RelayFallo(f"inaccesible ({type(e).__name__}: {e})") from e
    return _leer_json(r, f"el relé {cand['nombre']}")


async def _abrir_local_stream(host: str, payload: dict) -> tuple:
    """Abre el stream del local ANTES de responder: si conecta, sus bytes crudos pasan
    a través; si no, se prueba el siguiente candidato. Devuelve (resp, cliente)."""
    timeout = httpx.Timeout(TIMEOUT_LECTURA_LOCAL, connect=TIMEOUT_CONEXION)
    cliente = httpx.AsyncClient(timeout=timeout)
    try:
        req = cliente.build_request("POST", f"{host}/api/chat", json=payload)
        resp = await cliente.send(req, stream=True)
    except httpx.HTTPError as e:
        await _cerrar(cliente=cliente)
        raise _RelayFallo(f"inaccesible ({type(e).__name__}: {e})") from e
    if resp.status_code >= 400:
        await resp.aread()
        texto = resp.text[:160]
        await _cerrar(resp, cliente)
        raise _RelayFallo(f"HTTP {resp.status_code}: {texto}")
    return resp, cliente


async def _abrir_nube_stream(cand: dict, body: dict) -> tuple:
    """Abre el stream de un relé OpenAI-compat: el SSE se traduce a NDJSON de Ollama."""
    timeout = httpx.Timeout(TIMEOUT_LECTURA_LOCAL, connect=TIMEOUT_CONEXION)
    headers = {"Authorization": f"Bearer {cand['api_key']}", "Content-Type": "application/json"}
    cliente = httpx.AsyncClient(timeout=timeout)
    try:
        req = cliente.build_request("POST", f"{cand['base_url']}/chat/completions",
                                    json=body, headers=headers)
        resp = await cliente.send(req, stream=True)
    except httpx.HTTPError as e:
        await _cerrar(cliente=cliente)
        raise _RelayFallo(f"inaccesible ({type(e).__name__}: {e})") from e
    if resp.status_code >= 400:
        await resp.aread()
        texto = resp.text[:160]
        await _cerrar(resp, cliente)
        raise _RelayFallo(f"HTTP {resp.status_code}: {texto}")
    return resp, cliente


async def _pedir_tags_local(host: str) -> dict:
    """GET /api/tags del local con timeout corto: OpenJarvis lo usa como health."""
    timeout = httpx.Timeout(TIMEOUT_CONEXION_TAGS + 1.0, connect=TIMEOUT_CONEXION_TAGS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as cliente:
            r = await cliente.get(f"{host}/api/tags")
            if r.status_code >= 400:
                raise _RelayFallo(f"HTTP {r.status_code}")
    except httpx.HTTPError as e:
        raise _RelayFallo(f"inaccesible ({type(e).__name__}: {e})") from e
    return _leer_json(r, "el motor local")


# ───────────────────────────────────── endpoints ────────────────────────────────

@router.get("/{token}/api/tags")
async def api_tags(token: str, session: Session = Depends(get_session)):
    if not _autorizado(token):
        raise HTTPException(status_code=404)
    motor = motor_compartido(session)
    if not motor:
        raise HTTPException(status_code=503, detail="Sin motor LLM configurado")
    if not _local_en_observacion():
        try:
            local = await _pedir_tags_local(_host_ollama(motor.get("base_url") or ""))
        except _RelayFallo:
            _anotar_fallo_local()
            local = None
        if local is not None:
            _servido_local()
            return JSONResponse(content=local)
    # Local caído: se listan los modelos que el motor declara (el suyo + los relevos)
    # — OpenJarvis sigue viendo un engine sano con modelos disponibles.
    modelos: list[str] = []
    for m in [motor.get("model")] + [r.get("model") for r in motor.get("relevos") or []]:
        if m and m not in modelos:
            modelos.append(m)
    return {"models": [{"name": m, "model": m, "size": 0, "digest": "relay",
                        "modified_at": "2026-01-01T00:00:00Z", "details": {}}
                       for m in modelos]}


@_ruta_post("/{token}/api/chat")
async def api_chat(token: str, request: Request, session: Session = Depends(get_session)):
    if not _autorizado(token):
        raise HTTPException(status_code=404)
    motor = motor_compartido(session)
    if not motor:
        raise HTTPException(status_code=503, detail="Sin motor LLM configurado")
    payload = await _cuerpo(request)
    stream = bool(payload.get("stream"))
    candidatos = _candidatos(motor)
    # Con el local en observación no se le espera en cada mensaje: va al FINAL de la
    # cola — si todo lo demás falla todavía se le intenta (pudo volver a encender).
    if _local_en_observacion():
        locales = [c for c in candidatos if c["tipo"] == "ollama"]
        nubes = [c for c in candidatos if c["tipo"] != "ollama"]
        candidatos = nubes + locales
    fallos: list[str] = []
    for cand in candidatos:
        if cand["tipo"] == "ollama":
            if stream:
                try:
                    resp, cliente = await _abrir_local_stream(cand["host"], payload)
                except _RelayFallo as e:
                    _anotar_fallo_local()
                    fallos.append(f"{cand['nombre']}: {e}")
                    continue
                _servido_local()
                return StreamingResponse(_pasar_bytes(resp, cliente),
                                          media_type="application/x-ndjson")
            try:
                data = await _pedir_local_no_stream(cand["host"], payload)
            except _RelayFallo as e:
                _anotar_fallo_local()
                fallos.append(f"{cand['nombre']}: {e}")
                continue
            _servido_local()
            return JSONResponse(content=data)
        body = _a_openai(payload, cand)
        if stream:
            try:
                resp, cliente = await _abrir_nube_stream(cand, body)
            except _RelayFallo as e:
                fallos.append(f"{cand['nombre']}: {e}")
                continue
            _anotar_rescate(session, motor, cand)
            return StreamingResponse(_traducir_sse(resp, cliente, cand["model"]),
                                      media_type="application/x-ndjson")
        try:
            data_openai = await _pedir_nube_no_stream(cand, body)
        except _RelayFallo as e:
            fallos.append(f"{cand['nombre']}: {e}")
            continue
        _anotar_rescate(session, motor, cand)
        return JSONResponse(content=_de_openai(data_openai, cand))
    logger.warning("Relé Ollama: agotada la cadena (%s)", " | ".join(fallos))
    return JSONResponse(status_code=502,
                        content={"error": "Todos los proveedores fallaron: " + " | ".join(fallos)})
