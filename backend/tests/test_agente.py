"""Test del loop del agente (capa B) con un LLM simulado — sin proveedor ni BBDD real.

Verifica: (1) el agente llama tools y las ejecuta, (2) la identidad gatea la
revelación de citas, (3) tras la tool produce respuesta final.
"""
import json
from types import SimpleNamespace

from application.services.agente_service import AgenteService


class _FakeLLM:
    """Devuelve respuestas predefinidas en orden, ignorando el input."""
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)

    def chat(self, messages, tools=None, **kw):
        return self.respuestas.pop(0)


class _SesionSoloAuditoria:
    """Sesión sin datos: las lecturas (config del agente) vuelven vacías, y lo único que se
    puede escribir es la auditoría. Si el rechazo fallara y el agente intentara crear una
    cita o un presupuesto, el `add` de ese objeto revienta el test."""
    def exec(self, stmt):
        return _Vacio()

    def execute(self, *a, **k):
        return _Vacio()

    def get(self, *a, **k):
        return None

    def add(self, obj):
        assert type(obj).__name__ == "Auditoria", f"no debe escribir {type(obj).__name__}"

    def commit(self):
        pass

    def __getattr__(self, nombre):
        raise AssertionError(f"el rechazo debe ocurrir antes de usar session.{nombre}")


class _Vacio:
    def first(self):
        return None

    def all(self):
        return []

    def scalar(self):
        return 0


def _svc():
    # AgenteService sin tocar BBDD: parcheamos los métodos de com que usan sesión, más
    # _historial_conversacion (lee self.session.exec directamente, no pasa por com).
    svc = AgenteService.__new__(AgenteService)
    # _historial_conversacion (memoria de Alex, añadida en 2fc85d8) consulta la BD real vía
    # self.session.exec(...).first() — este test es deliberadamente sin BBDD real, así que se
    # simula "sin conversación previa" (primer mensaje del hilo).
    svc.session = SimpleNamespace(exec=lambda stmt: SimpleNamespace(first=lambda: None, all=lambda: []),
                                  get=lambda *a, **k: None,  # _datos_centro: sin centro → {}
                                  add=lambda obj: None, commit=lambda: None)  # auditoría de acciones
    com = SimpleNamespace()
    com.match_paciente = lambda c, t: (SimpleNamespace(id=4767), 1)
    com._nombres_por_telefono = lambda c, t: ["Juan Antonio Manzanedo Delgado"]
    com._proximas_citas = lambda c, pid, limit=3: [
        SimpleNamespace(fecha=__import__("datetime").date(2026, 7, 1), hora="10:00", confirmada=False)]
    com._escalar = lambda c, t, m: None
    com.enviar_texto = lambda c, t, x, generado_por_ia=False: (_ for _ in ()).throw(Exception("no-evo"))
    svc.com = com
    svc._historial_conversacion = lambda centro_id, telefono, limite=10: []
    return svc


def _tool_call(name, args):
    return {"role": "assistant", "tool_calls": [
        {"id": "1", "type": "function",
         "function": {"name": name, "arguments": json.dumps(args)}}]}


def test_agente_verifica_identidad_y_da_citas():
    llm = _FakeLLM([
        _tool_call("verificar_identidad", {"nombreCompleto": "Juan Antonio Manzanedo"}),
        _tool_call("consultar_mis_citas", {}),
        {"role": "assistant", "content": "Tu próxima cita es el 1 de julio a las 10:00."},
    ])
    res = _svc().responder(1, "34648085696", "¿cuándo tengo cita? Soy Juan Antonio Manzanedo", llm=llm)
    assert res["flujo"] == "agente"
    assert "julio" in res["respuesta"]
    # no se envía (Evolution simulado lanza) pero la respuesta se calcula
    assert res["respondido"] is False


def test_citas_bloqueadas_sin_identidad():
    svc = _svc()
    ctx = {"centro_id": 1, "telefono": "x", "paciente": SimpleNamespace(id=4767),
           "nombres": ["Juan Antonio Manzanedo Delgado"], "identidad": False}
    out = svc.ejecutar_tool("consultar_mis_citas", {}, ctx)
    assert json.loads(out)["error"] == "identidad_no_verificada"


def test_identidad_un_solo_nombre_no_basta():
    svc = _svc()
    ctx = {"centro_id": 1, "telefono": "x", "paciente": None,
           "nombres": ["Juan Antonio Manzanedo Delgado"], "identidad": False}
    out = svc.ejecutar_tool("verificar_identidad", {"nombreCompleto": "Juan"}, ctx)
    assert json.loads(out)["verificado"] is False
    assert ctx["identidad"] is False


# ─────────────────────── Frontera paciente/staff (PATIENT_ALLOWED_TOOLS) ───────────────────────
def test_tools_para_paciente_excluye_buscar_paciente_y_crear_presupuesto():
    """Con capacidades None (sin config) la lista blanca de paciente debe seguir aplicando —
    antes de este fix, esa rama devolvía TODAS las tools sin filtrar."""
    from application.services.agente_service import PATIENT_ALLOWED_TOOLS
    svc = AgenteService.__new__(AgenteService)
    svc.session = _SesionSoloAuditoria()
    svc._capacidades = lambda centro_id: None
    nombres_paciente = {t["function"]["name"] for t in svc._tools_para(1, es_staff=False)}
    nombres_staff = {t["function"]["name"] for t in svc._tools_para(1, es_staff=True)}
    assert nombres_paciente == PATIENT_ALLOWED_TOOLS
    assert "buscar_paciente" not in nombres_paciente
    assert "crear_presupuesto" not in nombres_paciente
    assert "buscar_paciente" in nombres_staff
    assert "crear_presupuesto" in nombres_staff


def test_tools_para_paciente_respeta_capacidades_y_lista_blanca_a_la_vez():
    """Con crear_presupuesto=True en capacidades, staff ve las 3 herramientas del protocolo
    de presupuesto; paciente NUNCA ve buscar_paciente/crear_presupuesto aunque la capacidad
    esté activada — la lista blanca manda por encima de las capacidades del centro."""
    svc = AgenteService.__new__(AgenteService)
    svc.session = _SesionSoloAuditoria()
    svc._capacidades = lambda centro_id: {"crear_presupuesto": True}
    nombres_paciente = {t["function"]["name"] for t in svc._tools_para(1, es_staff=False)}
    nombres_staff = {t["function"]["name"] for t in svc._tools_para(1, es_staff=True)}
    assert nombres_paciente == {"verificar_identidad", "buscar_tratamientos"}
    assert nombres_staff == {"verificar_identidad", "buscar_paciente", "buscar_tratamientos", "crear_presupuesto"}


def test_buscar_paciente_rechaza_sin_contexto_staff():
    """Segunda barrera: aunque alguien llame ejecutar_tool directamente con ctx de paciente
    (sin pasar por _tools_para), la operación se rechaza igual."""
    svc = AgenteService.__new__(AgenteService)
    svc.session = _SesionSoloAuditoria()
    ctx = {"centro_id": 1, "telefono": "34600000000", "paciente": None,
           "nombres": [], "identidad": False, "simular": False}
    out = json.loads(svc.ejecutar_tool("buscar_paciente", {"nombreCompleto": "Juan Garcia"}, ctx))
    assert out["motivo"] == "no_autorizado"


def test_crear_presupuesto_rechaza_sin_contexto_staff():
    svc = AgenteService.__new__(AgenteService)
    svc.session = _SesionSoloAuditoria()
    ctx = {"centro_id": 1, "telefono": "34600000000", "paciente": SimpleNamespace(id=4767),
           "nombres": [], "identidad": True, "simular": False}
    out = json.loads(svc.ejecutar_tool("crear_presupuesto", {"lineas": [{"tratamiento_id": 1}]}, ctx))
    assert out["motivo"] == "no_autorizado"
    assert out["creado"] is False


def test_crear_presupuesto_sin_simular_en_ctx_tambien_rechaza():
    """Fail-closed: si el ctx no trae 'simular' en absoluto (p.ej. un caller que se olvidó de
    pasarlo), se trata como paciente — nunca como staff por omisión."""
    svc = AgenteService.__new__(AgenteService)
    svc.session = _SesionSoloAuditoria()
    ctx = {"centro_id": 1, "telefono": "x", "paciente": SimpleNamespace(id=4767)}
    out = json.loads(svc.ejecutar_tool("crear_presupuesto", {"lineas": [{"tratamiento_id": 1}]}, ctx))
    assert out["motivo"] == "no_autorizado"


def test_crear_cita_paciente_conocido_identidad_false_no_crea_cita():
    """Regresión del hallazgo de auditoría: antes del fix, crear_cita solo comprobaba el
    hueco (ctx['huecos']), no la identidad — un teléfono que coincidía con un paciente real
    podía reservar una cita real sin haber pasado por verificar_identidad. La comprobación
    debe cortar ANTES de tocar self.session (por eso session=None es válido aquí: si el
    fix se rompe, este test lanzará un AttributeError sobre None en vez de fallar el assert,
    lo cual también delata la regresión)."""
    svc = AgenteService.__new__(AgenteService)
    svc.session = _SesionSoloAuditoria()
    ctx = {"centro_id": 1, "telefono": "34648085696", "paciente": SimpleNamespace(id=4767),
           "nombres": [], "identidad": False, "simular": False,
           "huecos": [{"fecha": "2026-09-18", "hora": "10:30", "colaboradorId": 1, "gabineteId": 1}]}
    out = json.loads(svc.ejecutar_tool("crear_cita", {"fecha": "2026-09-18", "hora": "10:30"}, ctx))
    assert out == {"error": "identidad_no_verificada"}
