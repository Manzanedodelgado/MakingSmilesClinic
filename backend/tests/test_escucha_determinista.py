"""Escucha activa: lo que llega al paciente y al doctor no depende de lo que alucine el LLM
(anatomía del diente, nº de raíces, cantidades de receta, precio inexistente)."""
import json
from decimal import Decimal
from unittest.mock import patch

from sqlmodel import Session

from application.services import consulta_service as cs
from domain.models.core import Paciente, Tratamiento
from domain.models.economico import PacienteTarifa, Tarifa, TarifaPrecio


def test_nombrar_piezas_marcador_y_correccion():
    assert cs.nombrar_piezas("Molestia en el [36].") == "Molestia en el primer molar inferior izquierdo (36)."
    assert cs.nombrar_piezas("la raíz del diente 36 (molar superior derecho)") == "la raíz del diente 36 (primer molar inferior izquierdo)"
    assert cs.nombrar_piezas("cita a las 10 (por la mañana)") == "cita a las 10 (por la mañana)"
    assert cs.nombrar_piezas("pieza [19]") == "pieza [19]"


def test_alinear_radicular():
    assert cs._alinear_radicular("Endodoncia unirradicular en 36", "MULTIRRADICULAR") == "Endodoncia multirradicular en 36"
    assert cs._alinear_radicular("ENDODONCIA BIRRADICULAR", "MULTIRRADICULAR") == "ENDODONCIA MULTIRRADICULAR"
    assert cs._alinear_radicular("Endodoncia unirradicular", None) == "Endodoncia unirradicular"


class _LLM:
    respuesta: dict = {}

    def __init__(self, _cfg):
        pass

    def chat(self, *a, **k):
        return {"content": json.dumps(self.respuesta)}


def test_escucha_completa_con_respuesta_alucinada(session: Session):
    pac = Paciente(centro_id=1, nombre="Escucha", apellidos="Prueba"); session.add(pac)
    endo = Tratamiento(centro_id=1, nombre="ENDODONCIA MULTIRRADICULAR", codigo="E1", activo=True)
    corona = Tratamiento(centro_id=1, nombre="CORONA SOBRE DIENTE", codigo="C1", activo=True)
    tar = Tarifa(centro_id=1, nombre="Privada"); session.add_all([endo, corona, tar]); session.commit()
    session.add(PacienteTarifa(paciente_id=pac.id, tarifa_id=tar.id, activo=True))
    session.add(TarifaPrecio(tarifa_id=tar.id, tratamiento_id=corona.id, precio=Decimal("400")))
    session.commit()
    _LLM.respuesta = {
        "soap": {"subjetivo": "Dolor al frío", "objetivo": "Caries en 36", "analisis": "Pulpitis irreversible",
                 "plan": "Endodoncia unirradicular en 36 y corona"},
        "tratamientos": [{"texto": "ENDODONCIA", "pieza": "36"}, {"texto": "CORONA SOBRE DIENTE", "pieza": "36"}],
        "receta": [{"medicamento": "Ibuprofeno 600 mg", "posologia": "1/8 h", "unidades": None, "envases": None}],
        "mensaje": "Tienes inflamación en el 36 (molar superior derecho). Haremos la endo del [36].",
    }
    with patch.object(cs, "LLMClient", _LLM), patch.object(cs, "_config_llm", lambda s, c: {}):
        r = cs.escuchar_visita(session, 1, pac.id, "dictado")

    assert r["soap"]["plan"] == "Endodoncia multirradicular en 36 y corona"
    assert "superior derecho" not in r["mensaje"]
    assert r["mensaje"] == ("Tienes inflamación en el 36 (primer molar inferior izquierdo). "
                            "Haremos la endo del primer molar inferior izquierdo (36).")
    lineas = {l["tratamiento"]: l for l in r["presupuesto"]}
    assert lineas["ENDODONCIA MULTIRRADICULAR"]["sin_precio"] is True and lineas["ENDODONCIA MULTIRRADICULAR"]["precio"] == 0.0
    assert lineas["CORONA SOBRE DIENTE"]["sin_precio"] is False and lineas["CORONA SOBRE DIENTE"]["precio"] == 400.0
    assert r["receta"][0]["unidades"] is None and r["receta"][0]["envases"] is None
