from fastapi.testclient import TestClient

from domain.models.agentes import CapacidadCatalogo
from sqlmodel import Session


def _crear_agente(client: TestClient, headers: dict) -> int:
    r = client.post("/agentes/db", json={"nombre": "Recepción", "audiencia": "staff", "rol_sub": "recepcion"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_catalogo_capacidades_lista_todas(client: TestClient, session: Session, token: str):
    session.add(CapacidadCatalogo(clave="probar_x", descripcion="d", ejecutor="e", parametros={}))
    session.commit()
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/agentes/db/capacidades/catalogo", headers=headers)
    assert r.status_code == 200, r.text
    claves = [c["clave"] for c in r.json()["capacidades"]]
    assert "probar_x" in claves


def test_patch_activo_y_programacion(client: TestClient, token: str):
    headers = {"Authorization": f"Bearer {token}"}
    agente_id = _crear_agente(client, headers)
    r = client.patch(f"/agentes/db/{agente_id}", json={
        "activo": True, "modo_activacion": "programado", "programacion": {"cron": "0 9 * * 1"},
    }, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["activo"] is True
    assert body["modo_activacion"] == "programado"
    assert body["programacion"] == {"cron": "0 9 * * 1"}


def test_patch_modo_activacion_invalido_rechazado(client: TestClient, token: str):
    headers = {"Authorization": f"Bearer {token}"}
    agente_id = _crear_agente(client, headers)
    r = client.patch(f"/agentes/db/{agente_id}", json={"modo_activacion": "inventado"}, headers=headers)
    assert r.status_code == 422


def test_personalidad_base_guardar_y_leer(client: TestClient, token: str):
    headers = {"Authorization": f"Bearer {token}"}
    agente_id = _crear_agente(client, headers)
    r = client.post(f"/agentes/db/{agente_id}/personalidad/base", json={"tono": "cercano", "cercania": 4}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["tono"] == "cercano"
    r2 = client.get(f"/agentes/db/{agente_id}/personalidad/base", headers=headers)
    assert r2.json()["personalidad"]["cercania"] == 4


def test_permisos_admin_grant_y_listar(client: TestClient, token: str):
    headers = {"Authorization": f"Bearer {token}"}
    agente_id = _crear_agente(client, headers)
    r = client.post(f"/agentes/db/{agente_id}/permisos", json={
        "rol_o_usuario": "doctores", "puede_ver": True, "puede_editar": True,
    }, headers=headers)
    assert r.status_code == 200, r.text
    r2 = client.get(f"/agentes/db/{agente_id}/permisos", headers=headers)
    permisos = r2.json()["permisos"]
    assert any(p["rol_o_usuario"] == "doctores" and p["puede_editar"] for p in permisos)


def test_canal_ajuste_guardar_y_leer(client: TestClient, token: str):
    headers = {"Authorization": f"Bearer {token}"}
    agente_id = _crear_agente(client, headers)
    r = client.post(f"/agentes/db/{agente_id}/canal/whatsapp", json={
        "longitud_max": 300, "usa_emojis": False, "ritmo": "Respuestas cortas y directas.",
    }, headers=headers)
    assert r.status_code == 200, r.text
    r2 = client.get(f"/agentes/db/{agente_id}/canal/whatsapp", headers=headers)
    ajuste = r2.json()["ajuste"]
    assert ajuste["longitud_max"] == 300
    assert ajuste["usa_emojis"] is False


def test_listar_no_lo_captura_la_ruta_generica_de_agentes_router(client: TestClient, token: str):
    """Regresión: agentes_router tiene GET /agentes/{agente_id}; si se registra antes que
    este router, "/agentes/db" se interpreta como agente_id="db" y nunca llega aquí."""
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/agentes/db", headers=headers)
    assert r.status_code == 200, r.text
    assert "agentes" in r.json()


def test_migrar_base_crea_los_cuatro_agentes_reales(client: TestClient, token: str):
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/agentes/db/migrar-base", headers=headers)
    assert r.status_code == 200, r.text
    nombres = {a["nombre"] for a in r.json()["agentes"]}
    assert nombres == {"Alex", "Victor", "Aura", "Gestor IA"}
    r2 = client.post("/agentes/db/migrar-base", headers=headers)
    assert r2.status_code == 200
    r3 = client.get("/agentes/db", headers=headers)
    assert len([a for a in r3.json()["agentes"] if a["es_agente_base"]]) == 4


def test_agente_de_otro_centro_no_es_visible(client: TestClient, session: Session, token: str):
    from domain.models.agentes import Agente
    from domain.models.core import Centro
    otro = Centro(nombre="Otro centro")
    session.add(otro); session.commit(); session.refresh(otro)
    ajeno = Agente(centro_id=otro.id, nombre="Ajeno", audiencia="staff", config_key="agente.ajeno")
    session.add(ajeno); session.commit(); session.refresh(ajeno)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.patch(f"/agentes/db/{ajeno.id}", json={"activo": True}, headers=headers)
    assert r.status_code == 404
