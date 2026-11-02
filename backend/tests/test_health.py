"""Tests del esqueleto + salud: /health (contrato del legado), /health/db y raíz."""
from fastapi.testclient import TestClient

from main import app


def test_health_responde_ok():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    # Contrato del legado: {api, database, llm, provider, model, details}
    assert body["api"] == "ok"
    assert body["database"] in ("ok", "error")
    assert "details" in body


def test_health_db_responde_ok():
    client = TestClient(app)
    resp = client.get("/health/db")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_raiz_responde():
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "MakingSmilesClinic API"
