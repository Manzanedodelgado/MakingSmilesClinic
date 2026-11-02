"""Correcciones del 23-oct-2026.

· El rescate de los agentes no manda datos a nubes gratuitas que entrenan (Gemini free,
  OpenRouter :free) salvo que se active a propósito.
· Aura no ofrece todas sus herramientas cuando las de la BD no casan con el código.
"""
from infrastructure.llm import ollama_provider as op


def _nombres(monkeypatch, entrena: bool) -> list[str]:
    from domain.config.settings import settings
    monkeypatch.setattr(settings, "groq_api_key", "g")
    monkeypatch.setattr(settings, "gemini_api_key_free", "m")
    monkeypatch.setattr(settings, "openrouter_api_key", "o")
    monkeypatch.setattr(settings, "rescate_nube_que_entrena", entrena)
    op.reiniciar_proveedor_llm()
    prov = op.get_llm_provider()
    return [getattr(p, "name", None) or getattr(p, "_name", None) or type(p).__name__ for p in getattr(prov, "_providers", [prov])]


def test_rescate_por_defecto_solo_groq(monkeypatch):
    nombres = _nombres(monkeypatch, entrena=False)
    assert "gemini" not in nombres and "openrouter" not in nombres
    assert "groq" in nombres


def test_rescate_que_entrena_solo_si_se_activa(monkeypatch):
    nombres = _nombres(monkeypatch, entrena=True)
    assert {"groq", "gemini", "openrouter"} <= set(nombres)


def test_aura_sin_coincidencias_no_ofrece_nada(monkeypatch):
    from application.services import aura_agente, capacidades_service
    monkeypatch.setattr(capacidades_service, "herramientas_base",
                        lambda s, c, a: [{"function": {"name": "no_existe_en_codigo"}}])
    a = aura_agente.AuraAgente.__new__(aura_agente.AuraAgente)
    a.s, a.centro_id = None, 1
    assert a.herramientas() == []
