"""PLAN B de los operadores de OpenJarvis: el relé Ollama del backend.

Si pc-escaner cae, /ollama/<token>/api/* sigue respondiendo con la misma forma que
Ollama (cruda si el local vive; traducida desde los relevos en la nube si no). Todo
con los seams de red parcheados: sin llamadas externas.
"""
import time

import pytest

import api.ollama_relay_router as relay
from domain.config.settings import settings
from domain.models.auditoria import Auditoria
from sqlmodel import select

TOKEN = "tok-relay-prueba"

MOTOR = {
    "base_url": "http://motor-prueba:11434/v1",
    "model": "qwen3.5-64k:latest",
    "api_key": "ollama-local-no-auth",
    "relevos": [
        {"nombre": "groq", "model": "qwen/qwen3.8-27b", "api_key": "kg",
         "base_url": "https://groq.test/v1"},
        {"nombre": "gemini", "model": "gemini-2.5-flash", "api_key": "kge",
         "base_url": "https://gem.test/v1beta/openai"},
    ],
    "centro_id": 1,
}

LOCAL_RESP = {"model": "qwen3.5-64k:latest", "created_at": "2026-10-14T10:00:00Z",
              "message": {"role": "assistant", "content": "hola local"},
              "done": True, "done_reason": "stop"}

NUBE_RESP = {"model": "qwen/qwen3.8-27b",
             "choices": [{"message": {"role": "assistant", "content": "hola nube"},
                          "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

CHAT = {"model": "qwen3.5-64k:latest",
        "messages": [{"role": "user", "content": "hola"}], "stream": False,
        "options": {"temperature": 0.2, "num_predict": 500}}


class _RelayFallo(relay._RelayFallo):
    """Marca interna para distinguir los fallos simulados de los reales."""


class _FakeStream:
    """Respuesta HTTP simulada para los seams de stream (aiter_lines)."""

    def __init__(self, lineas):
        self._lineas = lineas

    async def aiter_lines(self):
        for linea in self._lineas:
            yield linea

    async def aclose(self):
        pass


class _FakeRaw:
    """Igual pero en crudo (pasarela del local: aiter_raw)."""

    def __init__(self, trozos):
        self._trozos = trozos

    async def aiter_raw(self):
        for trozo in self._trozos:
            yield trozo

    async def aclose(self):
        pass


class _FakeCliente:
    async def aclose(self):
        pass


@pytest.fixture(autouse=True)
def estado_relé():
    """Memoria (observación del local + transición auditada) a cero en cada test."""
    relay._ULTIMO_FALLO_LOCAL = 0.0
    relay._AUDITADO = None
    yield
    relay._ULTIMO_FALLO_LOCAL = 0.0
    relay._AUDITADO = None


@pytest.fixture(name="token_relay")
def token_relay_fixture(monkeypatch):
    monkeypatch.setattr(settings, "ollama_relay_token", TOKEN)
    return TOKEN


@pytest.fixture(name="motor")
def motor_fixture(monkeypatch):
    monkeypatch.setattr(relay, "motor_compartido", lambda session: dict(MOTOR))


def _local_caido(monkeypatch, motivo="PC apagado"):
    def fake(host, payload):
        raise _RelayFallo(motivo)
    monkeypatch.setattr(relay, "_pedir_local_no_stream", fake)

    async def fake_stream(host, payload):
        raise _RelayFallo(motivo)
    monkeypatch.setattr(relay, "_abrir_local_stream", fake_stream)


def _local_vivo(monkeypatch, respuesta=LOCAL_RESP):
    async def fake(host, payload):
        return dict(respuesta)
    monkeypatch.setattr(relay, "_pedir_local_no_stream", fake)

    async def fake_stream(host, payload):
        return _FakeRaw([b'{"message":{"content":"x"},"done":false}\n',
                         b'{"done":true}\n']), _FakeCliente()
    monkeypatch.setattr(relay, "_abrir_local_stream", fake_stream)


def _nube_viva(monkeypatch, respuesta=NUBE_RESP):
    registrados = []

    async def fake(cand, body):
        registrados.append((cand["nombre"], body))
        return dict(respuesta)
    monkeypatch.setattr(relay, "_pedir_nube_no_stream", fake)

    async def fake_stream(cand, body):
        registrados.append((cand["nombre"], body))
        return _FakeStream([
            'data: {"choices":[{"index":0,"delta":{"content":"Hola "}}]}',
            '',
            'data: {"choices":[{"index":0,"delta":{"content":"mundo"}}]}',
            'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
            # Groq/OpenRouter/Gemini mandan el recuento final así (si el proveedor
            # no lo manda, el done del relé sale igual, sin los contadores).
            'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":5}}',
            'data: [DONE]',
        ]), _FakeCliente()
    monkeypatch.setattr(relay, "_abrir_nube_stream", fake_stream)
    return registrados


def test_token_invalido_responde_404(client):
    assert client.post("/ollama/otro-token/api/chat", json=CHAT).status_code == 404
    assert client.get("/ollama/otro-token/api/tags").status_code == 404


def test_sin_token_configurado_ni_el_correcto_entra(client, monkeypatch):
    monkeypatch.setattr(settings, "ollama_relay_token", "")
    assert client.post(f"/ollama/{TOKEN}/api/chat", json=CHAT).status_code == 404
    assert client.get(f"/ollama/{TOKEN}/api/tags").status_code == 404


def test_tags_local_vivo_pasa_tal_cual(client, token_relay, motor, monkeypatch):
    esperado = {"models": [{"name": "qwen3.5-64k:latest", "size": 123}]}

    async def fake(host):
        return dict(esperado)
    monkeypatch.setattr(relay, "_pedir_tags_local", fake)
    resp = client.get(f"/ollama/{TOKEN}/api/tags")
    assert resp.status_code == 200 and resp.json() == esperado


def test_tags_local_caido_lista_los_modelos_del_motor(client, token_relay, motor, monkeypatch):
    async def fake(host):
        raise _RelayFallo("sin señal")
    monkeypatch.setattr(relay, "_pedir_tags_local", fake)
    resp = client.get(f"/ollama/{TOKEN}/api/tags")
    assert resp.status_code == 200
    nombres = {m["name"] for m in resp.json()["models"]}
    # OpenJarvis sigue viendo un engine sano: el modelo local + los de los relevos.
    assert nombres == {"qwen3.5-64k:latest", "qwen/qwen3.8-27b", "gemini-2.5-flash"}


def test_chat_local_vivo_es_pasarela_crua(client, token_relay, motor, monkeypatch):
    _local_vivo(monkeypatch)
    resp = client.post(f"/ollama/{TOKEN}/api/chat", json=CHAT)
    assert resp.status_code == 200
    assert resp.json() == LOCAL_RESP   # idéntico, cero interpretación


def test_chat_local_caido_sirve_de_la_nube_con_forma_de_ollama(client, session,
                                                               token_relay, motor, monkeypatch):
    _local_caido(monkeypatch)
    _nube_viva(monkeypatch)
    resp = client.post(f"/ollama/{TOKEN}/api/chat", json=CHAT)
    assert resp.status_code == 200
    datos = resp.json()
    assert datos["message"]["content"] == "hola nube"
    assert datos["done"] is True and datos["done_reason"] == "stop"
    assert datos["model"] == "qwen/qwen3.8-27b"
    assert datos["prompt_eval_count"] == 10 and datos["eval_count"] == 5
    # Queda constancia (auditoría) de con qué proveedor se está sirviendo.
    filas = session.exec(select(Auditoria).where(
        Auditoria.accion == "llm.relay_rescate")).all()
    assert len(filas) == 1
    assert filas[0].centro_id == 1
    assert filas[0].detalle["proveedor"] == "groq"


def test_audita_solo_la_transicion_no_cada_mensaje(client, session, token_relay,
                                                   motor, monkeypatch):
    _local_caido(monkeypatch)
    _nube_viva(monkeypatch)
    for _ in range(3):
        resp = client.post(f"/ollama/{TOKEN}/api/chat", json=CHAT)
        assert resp.status_code == 200
    filas = session.exec(select(Auditoria).where(
        Auditoria.accion == "llm.relay_rescate")).all()
    assert len(filas) == 1   # una caída de horas no debe inundar la BD


def test_stream_local_caido_traduce_sse_a_ndjson(client, token_relay, motor, monkeypatch):
    _local_caido(monkeypatch)
    _nube_viva(monkeypatch)
    resp = client.post(f"/ollama/{TOKEN}/api/chat", json={**CHAT, "stream": True})
    assert resp.status_code == 200
    import json as jsonlib
    lineas = [jsonlib.loads(l) for l in resp.text.splitlines() if l.strip()]
    assert lineas[0]["message"]["content"] == "Hola "
    assert lineas[0]["done"] is False
    assert lineas[1]["message"]["content"] == "mundo"
    assert lineas[-1]["done"] is True and lineas[-1]["done_reason"] == "stop"
    assert lineas[-1]["prompt_eval_count"] == 10


def test_stream_local_vivo_pasa_bytes_crudos(client, token_relay, motor, monkeypatch):
    _local_vivo(monkeypatch)
    resp = client.post(f"/ollama/{TOKEN}/api/chat", json={**CHAT, "stream": True})
    assert resp.status_code == 200
    assert resp.text == ('{"message":{"content":"x"},"done":false}\n'
                         '{"done":true}\n')


def test_cadena_agotada_responde_502_con_el_informe(client, token_relay, motor, monkeypatch):
    _local_caido(monkeypatch, motivo="PC apagado")

    async def nube_caida(cand, body):
        raise _RelayFallo(f"HTTP 500 de {cand['nombre']}")
    monkeypatch.setattr(relay, "_pedir_nube_no_stream", nube_caida)
    resp = client.post(f"/ollama/{TOKEN}/api/chat", json=CHAT)
    assert resp.status_code == 502
    texto = resp.json()["error"]
    assert "motor-local" in texto and "groq" in texto and "gemini" in texto


def test_local_en_observacion_no_se_espera_primero(client, token_relay, motor, monkeypatch):
    """Tras un fallo del local, los mensajes siguientes van DIRECTO a la nube:
    nadie paga el timeout del PC apagado en cada mensaje."""
    relay._ULTIMO_FALLO_LOCAL = time.monotonic()
    tocados = []

    async def local_tardado(host, payload):
        tocados.append(host)
        return dict(LOCAL_RESP)
    monkeypatch.setattr(relay, "_pedir_local_no_stream", local_tardado)
    _nube_viva(monkeypatch)
    resp = client.post(f"/ollama/{TOKEN}/api/chat", json=CHAT)
    assert resp.status_code == 200
    assert resp.json()["message"]["content"] == "hola nube"
    assert tocados == []   # el local ni se intentó (estaba en observación)


def test_local_se_intenta_igual_al_final_si_todo_lo_demas_falla(client, token_relay,
                                                                motor, monkeypatch):
    """Mismo observación, pero con TODO caído: el local se intenta igualmente al final
    (pudo volver a encender) — no se le escribe off como imposible."""
    relay._ULTIMO_FALLO_LOCAL = time.monotonic()
    orden = []

    async def nube_caida(cand, body):
        orden.append(cand["nombre"])
        raise _RelayFallo("nube mala")
    monkeypatch.setattr(relay, "_pedir_nube_no_stream", nube_caida)

    async def local_responde(host, payload):
        orden.append("local")
        return dict(LOCAL_RESP)
    monkeypatch.setattr(relay, "_pedir_local_no_stream", local_responde)
    resp = client.post(f"/ollama/{TOKEN}/api/chat", json=CHAT)
    assert resp.status_code == 200
    assert orden == ["groq", "gemini", "local"]


def test_mensajes_openai_casa_tool_calls_y_arguments():
    mensajes = [
        {"role": "user", "content": "¿Qué hora es?"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "hora", "arguments": {"zona": "ES"}}}]},
        {"role": "tool", "content": "12:00"},
    ]
    salida = relay._mensajes_openai(mensajes)
    assert salida[1]["tool_calls"][0]["id"] == "call_0"
    import json as jsonlib
    args = salida[1]["tool_calls"][0]["function"]["arguments"]
    assert isinstance(args, str) and jsonlib.loads(args) == {"zona": "ES"}
    # La nube exige tool_call_id aunque Ollama no lo traiga: se casa con el pendiente.
    assert salida[2]["tool_call_id"] == "call_0"


def test_a_openai_traduce_options_tools_y_modelo():
    cand = {"model": "qwen/qwen3.8-27b"}
    payload = {"messages": [{"role": "user", "content": "h"}],
               "options": {"temperature": 0.1, "num_predict": 321, "stop": ["FIN"]},
               "tools": [{"type": "function", "function": {"name": "hora"}}]}
    body = relay._a_openai(payload, cand)
    assert body["model"] == "qwen/qwen3.8-27b"
    assert body["max_tokens"] == 321 and body["temperature"] == 0.1
    assert body["stop"] == ["FIN"]
    assert body["tool_choice"] == "auto" and body["tools"] == payload["tools"]
    assert body["stream"] is False
    # Sin num_predict, el default del relé: no recortar de más.
    assert relay._a_openai({"messages": []}, cand)["max_tokens"] == relay.MAX_TOKENS_NUBE


def test_de_openai_devuelve_forma_ollama():
    data = {"model": "gemini-2.5-flash",
            "choices": [{"finish_reason": "tool_calls",
                         "message": {"role": "assistant", "content": "",
                                     "tool_calls": [{"id": "x1", "function": {
                                         "name": "hora",
                                         "arguments": "{\"zona\": \"ES\"}"}}]}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
    out = relay._de_openai(data, {"model": "qwen3.5-64k:latest"})
    assert out["done"] is True and out["done_reason"] == "tool_calls"
    assert out["message"]["tool_calls"][0]["function"]["arguments"] == {"zona": "ES"}
    assert out["prompt_eval_count"] == 7 and out["eval_count"] == 3


def test_host_ollama_quita_el_v1():
    assert relay._host_ollama("http://motor:11434/v1") == "http://motor:11434"
    assert relay._host_ollama("http://motor:11434/v1/") == "http://motor:11434"
    assert relay._host_ollama("http://motor:11434") == "http://motor:11434"
