"""App doctor — protocolo fotográfico: referencias de guías y validación de tomas obligatorias.

Cubre la fase 1 del asistente de estudios fotográficos:
  - GET /app/doctores/me/protocolo devuelve las 10 ranuras con `referencia` absoluta de API.
  - GET /app/doctores/me/protocolo/guias/{codigo} sirve la PNG (200 image/png) o 404.
  - POST /app/doctores/me/estudios/{id}/completar exige las tomas obligatorias (409 con la
    lista) salvo que se mande `forzar=true`.
"""
from fastapi.testclient import TestClient
from sqlmodel import Session

from domain.models.core import Paciente
from domain.services import protocolo_ortodoncia as proto

BASE = "/app/doctores/me"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Centro-Id": "1"}


def _crear_estudio(client: TestClient, token: str, session: Session) -> int:
    pac = Paciente(centro_id=1, nombre="Paciente", apellidos="Protocolo Foto")
    session.add(pac)
    session.commit()
    session.refresh(pac)
    r = client.post(f"{BASE}/estudios", headers=_headers(token),
                    json={"paciente_id": pac.id, "etapa": "inicial"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ─────────────────────────── protocolo ───────────────────────────
def test_protocolo_devuelve_10_ranuras_con_referencia(client: TestClient, token: str):
    r = client.get(f"{BASE}/protocolo", headers=_headers(token))
    assert r.status_code == 200, r.text
    data = r.json()

    assert len(data["protocolo"]) == 10
    assert data["obligatorias"] == proto.CODIGOS_OBLIGATORIOS
    for slot in data["protocolo"]:
        codigo = slot["codigo"]
        assert slot["referencia"] == f"{BASE}/protocolo/guias/{codigo}.png", codigo
        # El contrato con las apps no pierde ningún campo previo.
        for campo in ("nombre", "grupo", "orden", "obligatoria", "overlay",
                      "orientacion", "instrucciones", "checklist"):
            assert campo in slot, (codigo, campo)


# ─────────────────────────── guías (PNG) ───────────────────────────
def test_guia_existente_devuelve_png(client: TestClient, token: str):
    r = client.get(f"{BASE}/protocolo/guias/frontal_reposo", headers=_headers(token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(r.content) > 1000


def test_guia_con_extension_png_devuelve_png(client: TestClient, token: str):
    """La `referencia` publicada incluye ".png": pedirla TAL CUAL también debe servir.

    (Regresión: el endpoint validaba el parámetro sin normalizar la extensión, así que
    el cliente que pedía la referencia del contrato recibía 404.)"""
    r = client.get(f"{BASE}/protocolo/guias/frontal_reposo.png", headers=_headers(token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_todas_las_guias_del_protocolo_existen(client: TestClient, token: str):
    for slot in proto.PROTOCOLO:
        r = client.get(f"{BASE}/protocolo/guias/{slot['codigo']}", headers=_headers(token))
        assert r.status_code == 200, (slot["codigo"], r.status_code, r.text)


def test_guia_inexistente_da_404(client: TestClient, token: str):
    r = client.get(f"{BASE}/protocolo/guias/no_existe", headers=_headers(token))
    assert r.status_code == 404, r.text


def test_guia_sin_auth_da_401(client: TestClient):
    r = client.get(f"{BASE}/protocolo/guias/frontal_reposo")
    assert r.status_code == 401, r.text


# ─────────────────────────── completar estudio ───────────────────────────
def test_completar_sin_tomas_obligatorias_da_409_con_lista(client: TestClient, token: str,
                                                            session: Session):
    estudio_id = _crear_estudio(client, token, session)
    r = client.post(f"{BASE}/estudios/{estudio_id}/completar", headers=_headers(token), json={})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"] == "Faltan tomas obligatorias"
    assert body["faltan_obligatorias"] == proto.CODIGOS_OBLIGATORIOS

    # El estudio NO se cierra si faltan obligatorias.
    detalle = client.get(f"{BASE}/estudios/{estudio_id}", headers=_headers(token))
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["estado"] != "completado"


def test_completar_con_forzar_cierra_el_estudio(client: TestClient, token: str, session: Session):
    estudio_id = _crear_estudio(client, token, session)
    r = client.post(f"{BASE}/estudios/{estudio_id}/completar", headers=_headers(token),
                    json={"notas": "Cerrado con forzar", "forzar": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado"] == "completado"
    assert body["notas"] == "Cerrado con forzar"
