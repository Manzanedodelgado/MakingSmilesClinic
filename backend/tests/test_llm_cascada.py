"""PLAN B en la raíz LLMClient: si el motor local cae, la MISMA llamada baja por los
`relevos` de la config — Victor, Aura, La Consulta Viva, el Gestor y Radiología no
mueren con pc-escaner. Todo se prueba con httpx.post parcheado: sin red.
"""
import json
import time

import httpx
import pytest

from infrastructure.external_apis import llm_client as lc
from infrastructure.external_apis.llm_client import LLMClient, LLMError

CONFIG = {
    "base_url": "http://motor-local-prueba/v1",
    "api_key": "k-local",
    "model": "qwen3.5-64k:latest",
    "reasoning_effort": "none",
    "relevos": [
        {"nombre": "groq", "base_url": "https://groq.test/v1", "api_key": "kg",
         "model": "qwen/qwen3.8-27b"},
        {"nombre": "gemini", "base_url": "https://gem.test/v1beta/openai", "api_key": "kge",
         "model": "gemini-2.5-flash"},
    ],
}
MENSAJES = [{"role": "user", "content": "hola"}]


class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data if data is not None else {"error": "fallo"}
        if isinstance(self._data, Exception):
            self.text = str(self._data)
        else:
            self.text = json.dumps(self._data)

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


def _ok(contenido):
    return {"choices": [{"message": {"role": "assistant", "content": contenido}}]}


def _conectar(url):
    return httpx.ConnectError("rechazado", request=httpx.Request("POST", url))


def _instalar(monkeypatch, comportamiento):
    """Parchea httpx.post (la raíz real de las llamadas) y devuelve la lista de
    llamadas registradas: [(url, payload), …] en orden."""
    llamadas = []

    def post(url, json=None, headers=None, timeout=None):
        llamadas.append((url, json))
        resultado = comportamiento(url, json)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    monkeypatch.setattr("infrastructure.external_apis.llm_client.httpx.post", post)
    return llamadas


def _dormir_que_duerme(monkeypatch):
    """Sustituye time.sleep por un registrador: medir la cascada es medir sus esperas."""
    esperas = []
    monkeypatch.setattr(lc.time, "sleep", lambda s: esperas.append(s))
    return esperas


def test_primario_vivo_no_toca_los_relevos(monkeypatch):
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: _Resp(200, _ok("del primario")))
    salida = LLMClient(CONFIG).chat(MENSAJES)
    assert salida["content"] == "del primario"
    assert len(llamadas) == 1
    assert llamadas[0][0] == "http://motor-local-prueba/v1/chat/completions"


def test_primario_muerto_baja_al_primer_relé(monkeypatch):
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: (
        _conectar(url) if "motor-local" in url else _Resp(200, _ok("de groq"))))
    salida = LLMClient(CONFIG).chat(MENSAJES, tools=[{"type": "function",
                                                      "function": {"name": "hora"}}])
    assert salida["content"] == "de groq"
    urls = [u for u, _ in llamadas]
    # Primario y primer relé; el segundo relé ni se enteró.
    assert len(llamadas) == 2 and "groq.test" in urls[1] and "gem.test" not in "".join(urls)
    # El relé hereda tools (los agentes siguen siendo agénticos en la nube) y NO el
    # reasoning_effort del primario (es asunto del modelo local, no de la nube).
    assert llamadas[1][1]["tools"] and llamadas[1][1]["tool_choice"] == "auto"
    assert llamadas[0][1]["reasoning_effort"] == "none"
    assert "reasoning_effort" not in llamadas[1][1]


def test_memoria_empieza_por_el_que_funciono(monkeypatch):
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: (
        _conectar(url) if "motor-local" in url else _Resp(200, _ok("de groq"))))
    LLMClient(CONFIG).chat(MENSAJES)   # falla el primario → gana groq
    LLMClient(CONFIG).chat(MENSAJES)   # cliente NUEVO, misma memoria
    urls = [u for u, _ in llamadas]
    assert urls[2] == "https://groq.test/v1/chat/completions"   # empieza por groq
    assert urls.count("http://motor-local-prueba/v1/chat/completions") == 1  # no re-probar aún


def test_reintenta_el_primario_cada_n_llamadas(monkeypatch):
    estado = {"primario": "caido"}

    def comportamiento(url, cuerpo):
        if "motor-local" in url:
            if estado["primario"] == "caido":
                return _conectar(url)
            return _Resp(200, _ok("volvió el primario"))
        return _Resp(200, _ok("de groq"))

    llamadas = _instalar(monkeypatch, comportamiento)
    LLMClient(CONFIG).chat(MENSAJES)                       # 1: falla → groq
    for _ in range(lc.REINTENTAR_PRIMARIO_CADA - 1):       # va directo a groq
        LLMClient(CONFIG).chat(MENSAJES)
    assert not any("motor-local" in u for u, _ in llamadas[2:])

    estado["primario"] = "vivo"
    salida = LLMClient(CONFIG).chat(MENSAJES)              # toca re-probarlo
    assert any("motor-local" in u for u, _ in llamadas[2:])
    assert salida["content"] == "volvió el primario"       # y ya manda el primario


def test_429_del_primario_salta_al_relé_sin_dormir(monkeypatch):
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: (
        _Resp(429) if "motor-local" in url else _Resp(200, _ok("de groq"))))
    esperas = _dormir_que_duerme(monkeypatch)
    salida = LLMClient(CONFIG).chat(MENSAJES)
    assert salida["content"] == "de groq"
    # Con cascada, un fallo del primario salta ya al siguiente: sin backoffs largos.
    assert esperas == []


def test_5xx_del_primario_salta_al_relé_sin_dormir(monkeypatch):
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: (
        _Resp(503) if "motor-local" in url else _Resp(200, _ok("de groq"))))
    esperas = _dormir_que_duerme(monkeypatch)
    assert LLMClient(CONFIG).chat(MENSAJES)["content"] == "de groq"
    assert esperas == []
    assert len(llamadas) == 2


def test_sin_relevos_el_unico_candidato_conserva_los_reintentos(monkeypatch):
    """Retrocompatibilidad pura: una config sin relevos se comporta como siempre —
    reintentos con backoff ante un cable flojo, y error final si no hay remedio."""
    config = {"base_url": "http://solo-primario/v1", "model": "m"}
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: _conectar(url))
    esperas = _dormir_que_duerme(monkeypatch)
    with pytest.raises(LLMError, match="inaccesible"):
        LLMClient(config).chat(MENSAJES)
    assert len(llamadas) == lc.REINTENTOS
    assert esperas == [lc.BACKOFF_BASE * (2 ** i) for i in range(lc.REINTENTOS - 1)]


def test_5xx_del_ultimo_candidato_tambien_reintenta(monkeypatch):
    config = {"base_url": "http://solo-primario/v1", "model": "m"}
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: _Resp(500))
    esperas = _dormir_que_duerme(monkeypatch)
    with pytest.raises(LLMError, match="HTTP 500"):
        LLMClient(config).chat(MENSAJES)
    assert len(llamadas) == lc.REINTENTOS and len(esperas) == lc.REINTENTOS - 1


def test_todos_caídos_el_error_cuenta_a_todos(monkeypatch):
    def comportamiento(url, cuerpo):
        if "motor-local" in url:
            return _conectar(url)
        if "groq.test" in url:
            return _Resp(500)
        return _Resp(401, {"error": "bad key"})

    _instalar(monkeypatch, comportamiento)
    with pytest.raises(LLMError) as exc:
        LLMClient(CONFIG).chat(MENSAJES)
    texto = str(exc.value)
    assert "primario" in texto and "groq" in texto and "gemini" in texto


def test_retrocompatible_sin_relevos_y_atributos_del_primario(monkeypatch):
    config = {"base_url": "http://unico/v1", "api_key": "k", "model": "modelo-x",
              "reasoning_effort": "none"}
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: _Resp(200, _ok("ok")))
    cliente = LLMClient(config)
    assert cliente.base_url == "http://unico/v1"
    assert cliente.model == "modelo-x"
    assert cliente.reasoning_effort == "none"
    assert cliente.chat(MENSAJES)["content"] == "ok"
    assert llamadas[0][1]["reasoning_effort"] == "none"


def test_config_invalida_sigue_fallando_igual():
    with pytest.raises(LLMError, match="LLM no configurado"):
        LLMClient({"base_url": "", "model": "m"})
    with pytest.raises(LLMError, match="LLM no configurado"):
        LLMClient({"base_url": "http://x/v1", "model": ""})


def test_respuesta_ilegible_no_tumba_al_siguiente_relé(monkeypatch):
    """Un 200 con cuerpo no-JSON (o sin choices) cuenta como fallo de ESE candidato."""
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: (
        _Resp(200, ValueError("no es json")) if "motor-local" in url
        else _Resp(200, _ok("de groq"))))
    assert LLMClient(CONFIG).chat(MENSAJES)["content"] == "de groq"
    assert len(llamadas) == 2


def test_reiniciar_memoria_vuelve_al_primario(monkeypatch):
    _instalar(monkeypatch, lambda url, cuerpo: (
        _conectar(url) if "motor-local" in url else _Resp(200, _ok("de groq"))))
    LLMClient(CONFIG).chat(MENSAJES)
    lc.reiniciar_memoria()
    llamadas = []
    # Tras reiniciar, el orden vuelve a empezar por el primario.
    def post(url, json=None, headers=None, timeout=None):
        llamadas.append(url)
        if "groq" in url:
            return _Resp(200, _ok("de groq"))
        raise _conectar(url)
    monkeypatch.setattr("infrastructure.external_apis.llm_client.httpx.post", post)
    LLMClient(CONFIG).chat(MENSAJES)
    assert llamadas[0].startswith("http://motor-local")


def test_content_vacio_sin_tool_calls_cuenta_como_fallo_y_baja_al_siguiente(monkeypatch):
    """C2b (re-revisión, ronda 2): un candidato puede devolver HTTP 200 con `content`
    vacío/en blanco y SIN tool_calls — el caso real que lo originó es Ollama servido por
    /v1 (en vez de su API nativa, ya eliminada de gmail_ai_processor.py): por /v1 ignora el
    apagado de razonamiento y se queda "pensando" hasta agotar max_tokens, devolviendo 200
    con content="". Antes de este fix, `chat()` daba por bueno ese candidato (contrato
    rígido: 200 = éxito) y devolvía contenido vacío en silencio sin probar el relevo
    siguiente. Ahora debe tratarse como fallo de ESE candidato y bajar al siguiente."""
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: (
        _Resp(200, _ok("")) if "motor-local" in url else _Resp(200, _ok("de groq"))))
    salida = LLMClient(CONFIG).chat(MENSAJES)
    assert salida["content"] == "de groq"
    urls = [u for u, _ in llamadas]
    assert len(llamadas) == 2 and "motor-local" in urls[0] and "groq.test" in urls[1]


def test_content_vacio_con_tool_calls_SI_cuenta_como_exito(monkeypatch):
    """El chequeo de C2b no debe romper el flujo agéntico legítimo: un `content` vacío
    acompañado de `tool_calls` es una respuesta de function-calling normal, no un fallo."""
    def _con_tool_calls():
        return {"choices": [{"message": {"role": "assistant", "content": "",
                                         "tool_calls": [{"id": "1", "type": "function",
                                                        "function": {"name": "hora", "arguments": "{}"}}]}}]}
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: _Resp(200, _con_tool_calls()))
    salida = LLMClient(CONFIG).chat(MENSAJES, tools=[{"type": "function", "function": {"name": "hora"}}])
    assert salida["content"] == ""
    assert salida["tool_calls"][0]["function"]["name"] == "hora"
    assert len(llamadas) == 1   # se acepta a la primera, no se prueba ningún relevo


def test_content_vacio_en_todos_devuelve_llmerror(monkeypatch):
    """Si TODOS los candidatos devuelven 200 con content vacío (sin tool_calls), la cadena
    entera debe agotarse con LLMError — nunca un None/contenido vacío silencioso."""
    _dormir_que_duerme(monkeypatch)   # el final de la línea reintenta con backoff real
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: _Resp(200, _ok("")))
    with pytest.raises(LLMError):
        LLMClient(CONFIG).chat(MENSAJES)
    # primario (1) + relevo1 (1) + relevo2 con reintentos (REINTENTOS) del final de línea.
    assert len(llamadas) >= 3


def test_content_vacio_en_turno_de_cierre_tras_tool_calls_se_acepta_al_instante(monkeypatch):
    """Rotura-1 (re-revisión ronda 2, corregida en ronda 3): si `messages` YA incluye un
    mensaje de rol "tool" (resultado de una tool_call ejecutada en un turno anterior, el
    patrón del turno de cierre de agente_service.py: `cliente.chat(messages, tools=None,
    ...)`), un content vacío en ESTE turno es una respuesta legítima de "nada más que
    decir" — NO debe disparar el chequeo de C2b ni gastar los reintentos/cascada completa
    (eso añadía ~14s y cambiaba el comportamiento de servicios que no son el gestor de
    facturas). Debe aceptarse al instante, con una sola llamada al primario."""
    mensajes_con_historial_de_tools = MENSAJES + [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "hora", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "1", "content": "son las 10:00"},
    ]
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: _Resp(200, _ok("")))
    salida = LLMClient(CONFIG).chat(mensajes_con_historial_de_tools, tools=None)
    assert salida["content"] == ""
    assert len(llamadas) == 1   # UNA sola llamada: no se disparó ningún reintento/cascada


def test_content_vacio_en_turno_normal_sin_historial_de_tools_sigue_bajando_al_siguiente(monkeypatch):
    """Control: sin ningún mensaje previo de rol "tool"/tool_calls en el historial, el
    chequeo de C2b sigue activo con normalidad (no se ha desactivado para todo, solo para
    el caso real del turno de cierre)."""
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: (
        _Resp(200, _ok("")) if "motor-local" in url else _Resp(200, _ok("de groq"))))
    salida = LLMClient(CONFIG).chat(MENSAJES, tools=None)   # tools=None pero SIN historial de tools
    assert salida["content"] == "de groq"
    assert len(llamadas) == 2   # primario falló (vacío) → bajó al relevo, como C2b manda


def test_content_como_lista_no_rompe_la_cadena(monkeypatch):
    """Rotura-2 (re-revisión ronda 2, corregida en ronda 3): si `content` viene como una
    lista (contenido multimodal de algunos proveedores) en vez de string, el chequeo de
    C2b no debe lanzar AttributeError sin capturar — debe tratarlo como "no vacío" de forma
    segura y aceptar la respuesta, dejando que el consumidor valide el formato después."""
    def _contenido_lista():
        return {"choices": [{"message": {"role": "assistant",
                                         "content": [{"type": "text", "text": "hola"}]}}]}
    llamadas = _instalar(monkeypatch, lambda url, cuerpo: _Resp(200, _contenido_lista()))
    salida = LLMClient(CONFIG).chat(MENSAJES)
    assert salida["content"] == [{"type": "text", "text": "hola"}]
    assert len(llamadas) == 1   # no se lanzó ninguna excepción sin capturar; no bajó al relevo
