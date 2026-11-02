"""Tests del canal de voz: el agente en modo voz no envía por WhatsApp y devuelve
la respuesta (para TTS). LLM simulado, sin BBDD ni telefonía reales."""
from types import SimpleNamespace

from application.services.agente_service import AgenteService


class _FakeLLM:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.ult_max_tokens = None

    def chat(self, messages, tools=None, **kw):
        self.ult_max_tokens = kw.get("max_tokens")
        self.ult_system = messages[0]["content"]
        return self.respuestas.pop(0)


def _svc():
    svc = AgenteService.__new__(AgenteService)
    # _historial_conversacion (memoria de Alex, añadida en 2fc85d8) consulta la BD real vía
    # self.session.exec(...).first() — este test es deliberadamente sin BBDD real, así que se
    # simula "sin conversación previa" (primer mensaje del hilo), que es lo que ejercitan estos
    # tests de todas formas (turno único).
    svc.session = SimpleNamespace(exec=lambda stmt: SimpleNamespace(first=lambda: None, all=lambda: []),
                                  get=lambda *a, **k: None,  # _datos_centro: sin centro → {}
                                  add=lambda obj: None, commit=lambda: None)  # auditoría de acciones
    com = SimpleNamespace()
    com.match_paciente = lambda c, t: (SimpleNamespace(id=4767), 1)
    com._nombres_por_telefono = lambda c, t: ["Juan Antonio Manzanedo Delgado"]
    # si se intentara enviar, esto lanzaría → en modo voz NO debe llamarse
    com.enviar_texto = lambda *a, **k: (_ for _ in ()).throw(AssertionError("¡no debe enviar en voz!"))
    svc.com = com
    # lee self.session directamente (no pasa por com) — sin BBDD real en este test.
    svc._historial_conversacion = lambda centro_id, telefono, limite=10: []
    return svc


def test_voz_no_envia_y_devuelve_respuesta():
    llm = _FakeLLM([{"role": "assistant", "content": "Su cita es el lunes a las diez."}])
    res = _svc().responder(1, "34648085696", "¿cuándo tengo cita?", llm=llm, enviar=False, voz=True)
    assert res["respondido"] is False
    assert res["respuesta"] == "Su cita es el lunes a las diez."


def test_voz_aplica_brevedad_y_hint():
    llm = _FakeLLM([{"role": "assistant", "content": "Hecho."}])
    _svc().responder(1, "34648085696", "hola", llm=llm, enviar=False, voz=True)
    assert llm.ult_max_tokens == 160          # respuesta corta para TTS
    assert "TELÉFONO" in llm.ult_system       # se inyecta la nota de voz


def test_texto_normal_usa_tokens_largos():
    llm = _FakeLLM([{"role": "assistant", "content": "ok"}])
    _svc().responder(1, "34648085696", "hola", llm=llm, enviar=False, voz=False)
    assert llm.ult_max_tokens == 600
