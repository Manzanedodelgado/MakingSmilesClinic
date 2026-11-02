"""Secretos de integración: enmascarado y fusión a cualquier profundidad."""
import copy

from api.configuracion_centro_router import _MASK, _enmascarar, _fusionar_secretos

CONFIG = {"api_key": "k0", "model": "m",
          "ocr": {"api_key": "nv", "relevos": [{"nombre": "a", "api_key": "c1"}, {"nombre": "b", "api_key": "c2"}]},
          "oauth_borrado": {"client_id": "id", "client_secret": "s", "refresh_token": "t"}}


def test_enmascara_anidados():
    original = copy.deepcopy(CONFIG)
    m = _enmascarar("llm", CONFIG)
    assert m["api_key"] == _MASK and m["model"] == "m"
    assert m["ocr"]["api_key"] == _MASK
    assert [r["api_key"] for r in m["ocr"]["relevos"]] == [_MASK, _MASK]
    assert m["oauth_borrado"] == {"client_id": "id", "client_secret": _MASK, "refresh_token": _MASK}
    assert CONFIG == original  # no muta el original


def test_guardar_con_mascaras_conserva_secretos():
    assert _fusionar_secretos("llm", _enmascarar("llm", CONFIG), CONFIG) == CONFIG


def test_relevos_reordenados_conservan_su_secreto():
    nuevo = _enmascarar("llm", CONFIG)
    nuevo["ocr"]["relevos"].reverse()
    out = _fusionar_secretos("llm", nuevo, CONFIG)
    assert out["ocr"]["relevos"] == [{"nombre": "b", "api_key": "c2"}, {"nombre": "a", "api_key": "c1"}]


def test_secreto_nuevo_sustituye_al_previo():
    nuevo = _enmascarar("llm", CONFIG)
    nuevo["ocr"]["relevos"][0]["api_key"] = "nueva"
    assert _fusionar_secretos("llm", nuevo, CONFIG)["ocr"]["relevos"][0]["api_key"] == "nueva"
