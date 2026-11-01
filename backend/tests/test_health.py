"""Tests del esqueleto: la API arranca y /health responde."""
from fastapi.testclient import TestClient

from main import app


def test_health_responde_ok():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "MakingSmilesClinic API"


def test_raiz_responde():
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "MakingSmilesClinic API"
