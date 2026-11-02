"""Pipeline 2-etapas end-to-end con httpx mockeado (sin red, sin claves reales).

Demuestra que `extraer_desde_pdf` orquesta OCR→texto y normaliza al ground truth de la 1515.
Si este test pasa, las claves NVIDIA reales son CONFIGURACIÓN, no lógica (condición del usuario).
También cubre el intake (reprocesar_gasto) sobre SQLite para el bucket E (suplido) y F (no_factura).
"""
import json as jsonlib
from datetime import date
from decimal import Decimal

from sqlmodel import select

from application.services.extract_service import extraer_desde_pdf
from application.services.intake_service import IntakeService
from domain.models.gestoria import Gasto, GastoIncidencia

INTEG_LLM = {
    "base_url": "https://integrate.api.nvidia.com/v1",
    "model": "meta/llama-3.3-70b-instruct", "api_key": "",
    "ocr": {"base_url": "https://integrate.api.nvidia.com/v1",
            "model": "nvidia/nemoretriever-parse", "api_key": ""},
}
GT_TEXTO = {
    "proveedor": "SRCL Consenur S.L.U", "cif_emisor": "B86208824",
    "numero_factura": "LGFA2005203", "fecha": "10/02/2020",
    "base_imponible": 102.55, "iva_pct": 21, "suplido": 21.33, "total": 145.42,
}


class _FakeResp:
    def __init__(self, payload):
        self._p, self.status_code = payload, 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def _fake_post(url, json=None, headers=None, timeout=None):
    """Etapa 1 (OCR) si el modelo es nemoretriever; etapa 2 (texto) en otro caso."""
    if "nemoretriever" in (json or {}).get("model", ""):
        # Estructura REAL de nvidia/nemoretriever-parse: lista-de-listas (una por página) de bloques
        # {text, bbox, type}. El test ejercita el aplanado [[…]] de _bloques_a_texto.
        args = [[
            {"text": "SRCL CONSENUR S.L.U", "bbox": {"xmin": 0.10, "ymin": 0.05, "xmax": 1, "ymax": 0.1}, "type": "Title"},
            {"text": "Factura LGFA2005203", "bbox": {"xmin": 0.10, "ymin": 0.20, "xmax": 1, "ymax": 0.3}, "type": "Text"},
            {"text": "con C.I.F. B86208824", "bbox": {"xmin": 0.10, "ymin": 0.90, "xmax": 1, "ymax": 1}, "type": "Page-footer"},
        ]]
        return _FakeResp({"choices": [{"message": {"tool_calls": [
            {"function": {"name": "markdown_bbox", "arguments": jsonlib.dumps(args)}}]}}]})
    return _FakeResp({"choices": [{"message": {"content": jsonlib.dumps(GT_TEXTO)}}]})


def test_pipeline_2etapas_produce_ground_truth(monkeypatch):
    monkeypatch.setattr("infrastructure.external_apis.llm_client.httpx.post", _fake_post)
    out = extraer_desde_pdf(b"\x89fake-image-bytes", "image/jpeg", INTEG_LLM)
    assert out["cif_emisor"] == "B86208824"           # CIF del EMISOR (del pie), no del cliente
    assert out["numero_factura"] == "LGFA2005203"
    assert out["fecha"] == "2020-02-10"                # DD/MM/AAAA → ISO
    assert out["base_imponible"] == 102.55
    assert out["iva_pct"] == 21.0
    assert out["suplido"] == 21.33
    assert out["total"] == 145.42


def test_intake_bucket_e_rellena_suplido(session):
    g = Gasto(centro_id=1, fecha=date(2020, 2, 10), base_imponible=Decimal("102.55"),
              iva_pct=Decimal("21"), retencion=Decimal("0"), total=Decimal("145.42"),
              cif_emisor="B86208824", estado="revisar", proveedor_extraido="SRCL Consenur S.L.U")
    session.add(g)
    session.commit()
    session.refresh(g)
    out = IntakeService(session, 1).reprocesar_gasto(g.id, "E")
    session.refresh(g)
    assert out["ok"] is True
    assert float(g.suplido) == 21.33
    assert g.estado == "pendiente"


def test_intake_bucket_f_no_factura(session):
    g = Gasto(centro_id=1, fecha=date(2024, 9, 1), concepto="NÓMINA RECTIFICADA",
              total=Decimal("1000"), estado="revisar", proveedor_extraido="TRIDENTAL")
    session.add(g)
    session.commit()
    session.refresh(g)
    out = IntakeService(session, 1).reprocesar_gasto(g.id, "F", motivo="no_factura:nomina")
    session.refresh(g)
    assert g.estado == "no_factura"
    assert out["estadoNuevo"] == "no_factura"
    assert session.exec(select(GastoIncidencia).where(
        GastoIncidencia.centro_id == 1)).first() is not None
