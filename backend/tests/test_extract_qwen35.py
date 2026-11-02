"""Lectura de facturas con qwen3.5 (21-sep→22-oct-2026 no entró ninguna por correo).

Dos fallos encadenados en extract_service:
  · _client_texto tiraba `reasoning_effort` y `relevos`: el modelo razonaba y devolvía content vacío.
  · qwen3.5 escribe los importes a la española ("total": 6,34) y el JSON no se podía leer.
"""
from application.services import extract_service as ex


def test_cliente_texto_conserva_razonamiento_y_relevos(monkeypatch):
    monkeypatch.delenv("TXT_API_KEY", raising=False)
    integ = {"base_url": "http://ollama:11434/v1", "model": "qwen3.5-clinica:latest", "api_key": "k",
             "reasoning_effort": "none",
             "relevos": [{"nombre": "groq", "base_url": "https://api.groq.com/openai/v1",
                          "model": "qwen/qwen3.8-27b", "api_key": "g"}],
             "ocr": {"base_url": "https://ocr", "model": "nemotron-parse"}}
    cli = ex._client_texto(integ)
    assert cli.reasoning_effort == "none"
    assert len(cli.cadena) == 2          # primario + 1 relevo
    assert cli.cadena[1]["model"] == "qwen/qwen3.8-27b"


def test_json_con_decimales_a_la_espanola():
    content = '{\n  "proveedor": "A, B 5,24",\n  "base_imponible": 5,24,\n  "iva_pct": 21,\n  "total": 1.234,56\n}'
    d = ex._json_de_contenido(content)
    assert d["base_imponible"] == 5.24
    assert d["total"] == 1234.56
    assert d["proveedor"] == "A, B 5,24"   # los textos no se tocan


def test_json_valido_no_se_altera():
    assert ex._json_de_contenido('```json\n{"total": 6.34, "iva_pct": 21}\n```') == {"total": 6.34, "iva_pct": 21}
