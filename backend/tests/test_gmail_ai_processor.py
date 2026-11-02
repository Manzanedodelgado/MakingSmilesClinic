"""`GmailAIProcessor._llamar_ia_multimodal` usa `LLMClient` (infraestructura) con su
cadena de `relevos`, en vez del fallback propio que tenía antes. Contrato fijado por
Task 1 del plan de relevo multi-IA (ver .superpowers/sdd/2026-10-26-gestoria-ia-relevo-plan)."""
import asyncio

import httpx
from sqlmodel import select

from application.services.gmail_ai_processor import EmailCompleto, GmailAIProcessor
from domain.models.config import Integracion
from domain.models.gestoria import Gasto


def test_llamar_ia_multimodal_relevo_que_falla_pasa_al_siguiente(session, monkeypatch):
    """Si el candidato 'primario' no soporta el payload multimodal (p.ej. responde 400 por
    content con partes de imagen que no entiende), LLMClient debe saltar al relevo siguiente
    en vez de romper la llamada completa — mismo contrato que LLMClient.chat ya tiene hoy
    para HTTP 4xx no-rate-limit (ver test_llm_client_reasoning.py): este test solo confirma
    que GmailAIProcessor no añade ningún manejo propio que lo impida."""
    session.add(Integracion(centro_id=1, tipo="llm", agente="gestor_multimodal", activo=True,
                             config={"base_url": "https://openrouter.ai/api/v1", "api_key": "k1",
                                     "modelo": "google/gemini-2.5-flash",
                                     "relevos": [{"nombre": "texto-only", "base_url": "https://api.ejemplo/v1",
                                                  "api_key": "k2", "model": "modelo-sin-vision"}]}))
    session.commit()

    def fake_post(url, json, headers, timeout):
        if "ejemplo" in url:   # el relevo "texto-only" sí responde
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"accion": "descartado"}'}}]},
                                  request=httpx.Request("POST", url))
        return httpx.Response(400, text="payload multimodal no soportado",
                              request=httpx.Request("POST", url))   # el primario rechaza el payload
    monkeypatch.setattr("infrastructure.external_apis.llm_client.httpx.post", fake_post)

    proc = GmailAIProcessor(session, centro_id=1)
    resultado = asyncio.run(proc._llamar_ia_multimodal({
        "system_prompt": "sistema", "user_parts": [{"type": "text", "text": "hola"}],
        "config": proc.config_ia,
    }))
    assert resultado == {"accion": "descartado"}


def test_llamar_ia_multimodal_usa_llmclient_con_relevos(session, monkeypatch):
    """C2a (ronda 2 del fix): la config no especifica `modelo_fallback`/`base_url_fallback`
    propios, así que `obtener_config_centro` rellena `modelo_fallback` con el valor de
    catálogo de DEFAULT_CONFIG ("google/gemini-2.5-flash-lite", distinto del primario
    "google/gemini-2.5-flash") — ese ES el fallback real que el código original (antes de
    toda esta rama) añadía siempre que `modelo_fallback != modelo`, con `base_url_fallback`
    vacío = usar la base_url del PRIMARIO. Por eso la cadena esperada incluye
    'fallback_legacy' ANTES de los relevos nuevos configurados."""
    session.add(Integracion(centro_id=1, tipo="llm", agente="gestor_multimodal", activo=True,
                             config={"base_url": "https://openrouter.ai/api/v1", "api_key": "k1",
                                     "modelo": "google/gemini-2.5-flash",
                                     "relevos": [{"nombre": "groq", "base_url": "https://api.groq.com/openai/v1",
                                                  "api_key": "k2", "model": "qwen/qwen3.8-27b"}]}))
    session.commit()
    capturado = {}

    def fake_chat(self, messages, **kw):
        capturado["cadena"] = [c["nombre"] for c in self.cadena]
        return {"content": '{"accion": "descartado"}'}
    monkeypatch.setattr("infrastructure.external_apis.llm_client.LLMClient.chat", fake_chat)

    proc = GmailAIProcessor(session, centro_id=1)
    resultado = asyncio.run(proc._llamar_ia_multimodal({
        "system_prompt": "sistema", "user_parts": [{"type": "text", "text": "hola"}],
        "config": proc.config_ia,
    }))
    assert resultado == {"accion": "descartado"}
    assert capturado["cadena"] == ["primario", "fallback_legacy", "groq"]


def test_llamar_ia_multimodal_sin_api_key_devuelve_none(session):
    """Retrocompatible: sin integración 'gestor_multimodal' activa, sigue devolviendo
    None (mismo contrato de fallo que antes de usar LLMClient)."""
    proc = GmailAIProcessor(session, centro_id=1)
    resultado = asyncio.run(proc._llamar_ia_multimodal({
        "system_prompt": "sistema", "user_parts": [{"type": "text", "text": "hola"}],
        "config": proc.config_ia,
    }))
    assert resultado is None


def test_llamar_ia_multimodal_usa_fallback_legacy_cuando_relevos_vacio(session, monkeypatch):
    """C2 (revisión final de rama): si self.relevos está vacío (caso real de producción
    hoy), el fallback real anterior (modelo_fallback/base_url_fallback/api_key_fallback de
    la integración, antes servido por el `_pedir_a_ollama` ya eliminado) debe seguir
    disponible como relevo de LLMClient — no se pierde sin sustituto."""
    session.add(Integracion(centro_id=1, tipo="llm", agente="gestor_multimodal", activo=True,
                             config={"base_url": "https://openrouter.ai/api/v1", "api_key": "k1",
                                     "modelo": "google/gemini-2.5-flash",
                                     "modelo_fallback": "google/gemini-2.5-flash-lite",
                                     "base_url_fallback": "http://localhost:11434/v1",
                                     "api_key_fallback": "ollama-local"}))
    session.commit()
    capturado = {}

    def fake_chat(self, messages, **kw):
        capturado["cadena"] = [(c["nombre"], c["base_url"], c["model"]) for c in self.cadena]
        return {"content": '{"accion": "descartado"}'}
    monkeypatch.setattr("infrastructure.external_apis.llm_client.LLMClient.chat", fake_chat)

    proc = GmailAIProcessor(session, centro_id=1)
    assert proc.relevos == []   # caso real de producción: sin relevos nuevos configurados
    resultado = asyncio.run(proc._llamar_ia_multimodal({
        "system_prompt": "sistema", "user_parts": [{"type": "text", "text": "hola"}],
        "config": proc.config_ia,
    }))
    assert resultado == {"accion": "descartado"}
    assert capturado["cadena"] == [
        ("primario", "https://openrouter.ai/api/v1", "google/gemini-2.5-flash"),
        ("fallback_legacy", "http://localhost:11434/v1", "google/gemini-2.5-flash-lite"),
    ]


def test_llamar_ia_multimodal_fallback_legacy_antes_de_relevos_nuevos(session, monkeypatch):
    """C2: el fallback legacy va ANTES de los relevos nuevos configurados en self.relevos,
    para que siga siendo el primer Plan B (el orden que tenía antes de toda esta rama)."""
    session.add(Integracion(centro_id=1, tipo="llm", agente="gestor_multimodal", activo=True,
                             config={"base_url": "https://openrouter.ai/api/v1", "api_key": "k1",
                                     "modelo": "google/gemini-2.5-flash",
                                     "modelo_fallback": "google/gemini-2.5-flash-lite",
                                     "base_url_fallback": "http://localhost:11434/v1",
                                     "relevos": [{"nombre": "groq", "base_url": "https://api.groq.com/openai/v1",
                                                  "api_key": "k2", "model": "qwen/qwen3.8-27b"}]}))
    session.commit()
    capturado = {}

    def fake_chat(self, messages, **kw):
        capturado["cadena"] = [c["nombre"] for c in self.cadena]
        return {"content": '{"accion": "descartado"}'}
    monkeypatch.setattr("infrastructure.external_apis.llm_client.LLMClient.chat", fake_chat)

    proc = GmailAIProcessor(session, centro_id=1)
    resultado = asyncio.run(proc._llamar_ia_multimodal({
        "system_prompt": "sistema", "user_parts": [{"type": "text", "text": "hola"}],
        "config": proc.config_ia,
    }))
    assert resultado == {"accion": "descartado"}
    assert capturado["cadena"] == ["primario", "fallback_legacy", "groq"]


def test_llamar_ia_multimodal_sin_modelo_fallback_no_anade_relevo_legacy(session, monkeypatch):
    """Retrocompatible: si la config NO trae modelo_fallback (o usa el DEFAULT_CONFIG sin
    integración propia), no se inventa un relevo legacy de la nada."""
    from dataclasses import replace
    from domain.config.ia_multimodal import DEFAULT_CONFIG
    proc = GmailAIProcessor.__new__(GmailAIProcessor)
    proc.openrouter_key = "k"
    sin_fallback = replace(DEFAULT_CONFIG, modelo_fallback="")
    assert proc._relevo_fallback_legacy(sin_fallback) is None


def test_llamar_ia_multimodal_modelo_fallback_igual_al_primario_no_anade_relevo():
    """C2a: si modelo_fallback coincide con el primario, tampoco hay fallback real que
    añadir (sería el mismo modelo dos veces) — misma señal que usaba el código original."""
    from dataclasses import replace
    from domain.config.ia_multimodal import DEFAULT_CONFIG
    proc = GmailAIProcessor.__new__(GmailAIProcessor)
    proc.openrouter_key = "k"
    igual = replace(DEFAULT_CONFIG, modelo_fallback=DEFAULT_CONFIG.modelo)
    assert proc._relevo_fallback_legacy(igual) is None


def test_llamar_ia_multimodal_todos_los_candidatos_fallan_devuelve_none(session, monkeypatch):
    """Si ni el primario ni ningún relevo responden, LLMClient lanza LLMError y
    GmailAIProcessor debe capturarlo y devolver None (mismo contrato de fallo que el
    fallback propio anterior), sin propagar la excepción."""
    session.add(Integracion(centro_id=1, tipo="llm", agente="gestor_multimodal", activo=True,
                             config={"base_url": "https://openrouter.ai/api/v1", "api_key": "k1",
                                     "modelo": "google/gemini-2.5-flash"}))
    session.commit()

    def fake_post(url, json, headers, timeout):
        return httpx.Response(500, text="boom", request=httpx.Request("POST", url))
    monkeypatch.setattr("infrastructure.external_apis.llm_client.httpx.post", fake_post)
    monkeypatch.setattr("infrastructure.external_apis.llm_client.time.sleep", lambda *_: None)

    proc = GmailAIProcessor(session, centro_id=1)
    resultado = asyncio.run(proc._llamar_ia_multimodal({
        "system_prompt": "sistema", "user_parts": [{"type": "text", "text": "hola"}],
        "config": proc.config_ia,
    }))
    assert resultado is None


def test_procesar_webhook_gasto_sin_cif_ni_total_no_se_registra(session, monkeypatch):
    """I7 (revisión final de rama, riesgo residual documentado): si un futuro relevo sin
    capacidad de visión real devuelve accion='gasto' pero sin cif_emisor/total utilizables
    (cadena vacía o 0, no None — lo que el model_validator de GastoIAResponse no pilla), no
    debe registrarse como gasto real: se trata igual que 'IA no respondió'."""
    session.add(Integracion(centro_id=1, tipo="llm", agente="gestor_multimodal", activo=True,
                             config={"base_url": "https://openrouter.ai/api/v1", "api_key": "k1",
                                     "modelo": "google/gemini-2.5-flash"}))
    session.commit()
    proc = GmailAIProcessor(session, centro_id=1)

    async def fake_fetch(message_id):
        return EmailCompleto(message_id=message_id, uid="1", remitente="x@y.com", asunto="f",
                             fecha=__import__("datetime").date.today(), cuerpo_texto="",
                             cuerpo_html="", adjuntos=[], enlaces=[])
    monkeypatch.setattr(proc, "_fetch_email_completo", fake_fetch)

    async def fake_ia(payload):
        return {"accion": "gasto", "cif_emisor": "", "total": None, "confianza": "alta",
                "tipo_documento": "factura", "notas": "n" * 30, "destinatario": "Tridental",
                "proveedor_nombre": "Proveedor X", "numero_factura": "F1",
                "fecha_emision": "2024-01-01", "base_imponible": 100.0,
                "categoria_contable": "suministros", "origen_dato": "cuerpo_email"}
    monkeypatch.setattr(proc, "_llamar_ia_multimodal", fake_ia)

    resultado = asyncio.run(proc.procesar_webhook("<m1>"))
    assert resultado.ok is False
    assert resultado.accion == "error"
    assert session.exec(select(Gasto)).all() == []
