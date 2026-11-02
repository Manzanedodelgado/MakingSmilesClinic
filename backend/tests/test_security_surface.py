from fastapi.testclient import TestClient


def test_demo_api_apps_no_se_publica(client: TestClient):
    response = client.get("/apps/pacientes/1/ficha")
    assert response.status_code == 404


def test_api_schema_y_documentacion_se_desactivan_fuera_de_development():
    from main import _api_docs_options

    assert _api_docs_options("production", False) == {
        "docs_url": None, "redoc_url": None, "openapi_url": None,
    }
    assert _api_docs_options("production", True)["openapi_url"] == "/openapi.json"
    assert _api_docs_options("production", True)["docs_url"] is None
    assert _api_docs_options("development", False)["openapi_url"] == "/openapi.json"


def test_subida_rechaza_svg_activo(client: TestClient, token: str):
    response = client.post(
        "/uploads",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")},
    )
    assert response.status_code == 422


def test_subida_limited_a_10mb(client: TestClient, token: str):
    from api.uploads_router import MAX_BYTES

    response = client.post(
        "/uploads",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n" + b"x" * MAX_BYTES, "image/png")},
    )
    assert response.status_code == 413


def test_carga_png_requiere_firma_de_contenido():
    from api.uploads_router import _mime_valido

    assert _mime_valido("png", b"\x89PNG\r\n\x1a\ncontenido")
    assert not _mime_valido("png", b"<script>alert(1)</script>")
