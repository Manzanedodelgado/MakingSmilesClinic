"""Tests de la máquina de estados de WhatsApp (dominio puro, sin BBDD)."""
from domain.services import whatsapp_flujos as wf


# ─────────────────────────── INTENTS ───────────────────────────
def test_detectar_intent_basico():
    assert wf.detectar_intent("Tengo mucho dolor") == "urgencia"
    assert wf.detectar_intent("quiero cancelar mi cita") == "cancelar"
    assert wf.detectar_intent("¿cuándo es mi cita?") == "consultar"
    assert wf.detectar_intent("quiero pedir cita") == "reservar"
    assert wf.detectar_intent("sí, perfecto") == "confirmar"
    assert wf.detectar_intent("quiero hablar con una persona") == "handoff"
    assert wf.detectar_intent("buenos días") == "general"


def test_cancelar_tiene_precedencia_sobre_reservar():
    # "no puedo ir a la cita" contiene 'cita' (reservar) pero gana cancelar
    assert wf.detectar_intent("no puedo ir a la cita") == "cancelar"


# ─────────────────────────── IDENTIDAD ───────────────────────────
def test_identidad_exige_dos_tokens():
    fichas = ["Juan Antonio Manzanedo Delgado"]
    assert wf.verificar_identidad("Juan Antonio Manzanedo", fichas) is True
    assert wf.verificar_identidad("Manzanedo Delgado", fichas) is True
    # un solo nombre de pila NO basta (bug .37 corregido)
    assert wf.verificar_identidad("Juan", fichas) is False
    assert wf.verificar_identidad("Antonio", fichas) is False
    assert wf.verificar_identidad("", fichas) is False


# ─────────────────────────── FLUJOS ───────────────────────────
def test_urgencia_escala_y_corta_flujo():
    res = wf.manejar({"intent": "reservar", "paso": "tratamiento"}, "me duele muchísimo", {})
    assert res["accion"]["tipo"] == "escalar"
    assert res["accion"]["motivo"] == "urgencia"
    assert res["nuevo_estado"] is None


def test_confirmar_genera_accion_confirmar():
    res = wf.manejar(None, "sí, allí estaré", {})
    assert res["accion"] == {"tipo": "confirmar"}


def test_consultar_pide_nombre_y_luego_verifica():
    paso1 = wf.manejar(None, "¿cuándo tengo cita?", {})
    assert paso1["nuevo_estado"] == {"intent": "consultar", "paso": "verificar"}
    # paso 2: nombre correcto, con ficha → acción 'citas'
    ctx = {"tiene_paciente": True, "nombres": ["Juan Antonio Manzanedo Delgado"]}
    paso2 = wf.manejar(paso1["nuevo_estado"], "Juan Antonio Manzanedo", ctx)
    assert paso2["accion"]["tipo"] == "citas"


def test_consultar_identidad_fallida_escala():
    ctx = {"tiene_paciente": True, "nombres": ["Juan Antonio Manzanedo Delgado"]}
    res = wf.manejar({"intent": "consultar", "paso": "verificar"}, "Pedro", ctx)
    assert res["accion"]["tipo"] == "escalar"
    assert res["accion"]["motivo"] == "identidad_no_verificada"


def test_reservar_recoge_tratamiento_y_escala():
    paso1 = wf.manejar(None, "quiero pedir cita", {})
    assert paso1["nuevo_estado"] == {"intent": "reservar", "paso": "tratamiento"}
    paso2 = wf.manejar(paso1["nuevo_estado"], "limpieza", {})
    assert paso2["accion"]["tipo"] == "escalar"
    assert paso2["accion"]["detalle"] == "limpieza"
