"""Alta de paciente → carpeta en Drive (num_historia + apellidos + nombre, con RX e Imágenes)."""
import pytest
from sqlmodel import Session

from api import romexis_router
from application.services.multimedia_service import MultimediaService
from domain.models.config import Integracion
from domain.models.core import Paciente
from infrastructure.external_apis import drive_client

CFG = {"sa_b64": "x", "carpetas": {"pacientes": "ROOT"}}


@pytest.fixture
def drive(session: Session, monkeypatch):
    session.add(Integracion(centro_id=1, tipo="google_drive", activo=True, config=CFG))
    session.commit()
    llamadas = {"crear": [], "buscar": []}
    monkeypatch.setattr(drive_client, "configurado", lambda c: bool(c))
    monkeypatch.setattr(drive_client, "buscar_subcarpeta_prefijo",
                        lambda cfg, parent, pref: llamadas["buscar"].append((parent, pref)) or llamadas.get("existe"))
    def crear(cfg, nombre, parent):
        llamadas["crear"].append((nombre, parent)); return f"id:{nombre}"
    monkeypatch.setattr(drive_client, "buscar_o_crear_carpeta", crear)
    return llamadas


def _pac(session, nh="7001", centro=1):
    p = Paciente(centro_id=centro, num_historia=nh, nombre="Ana", apellidos="Lopez Ruiz", activo=True)
    session.add(p); session.commit(); session.refresh(p); return p


def test_crea_carpeta_y_subcarpetas(session, drive):
    pac = _pac(session)
    assert MultimediaService(session).crear_carpeta_drive(1, pac) == "id:7001 Lopez Ruiz Ana"
    assert drive["crear"][0] == ("7001 Lopez Ruiz Ana", "ROOT")
    assert [c[0] for c in drive["crear"][1:]] == ["RX", "Imágenes"]


def test_idempotente_reutiliza_carpeta_existente(session, drive):
    drive["existe"] = "CARPETA_YA_EXISTENTE"
    pac = _pac(session)
    assert MultimediaService(session).crear_carpeta_drive(1, pac) == "CARPETA_YA_EXISTENTE"
    assert [c[0] for c in drive["crear"]] == ["RX", "Imágenes"]     # no crea otra carpeta de paciente
    assert drive["buscar"][0] == ("ROOT", "7001 ")


def test_no_cruza_centros_y_no_lanza(session, drive, monkeypatch):
    pac = _pac(session)
    assert MultimediaService(session).crear_carpeta_drive(2, pac) is None     # centro distinto
    monkeypatch.setattr(drive_client, "buscar_o_crear_carpeta",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("drive caído")))
    assert MultimediaService(session).crear_carpeta_drive(1, pac) is None     # best-effort


def test_alta_lanza_tarea_drive_y_no_depende_de_ella(client, token, session, monkeypatch):
    vistas = []
    monkeypatch.setattr(romexis_router, "_crear_carpeta_drive_bg", lambda pid, cid: vistas.append((pid, cid)))
    r = client.post("/pacientes/nuevo", json={"nombre": "Eva", "apellidos": "Gil"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert vistas == [(r.json()["id"], 1)] and r.json()["romexis_sync_id"]
