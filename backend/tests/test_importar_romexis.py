"""Endpoint /radiologia/importar-romexis-interno: recibe imágenes del bridge de Romexis.
Auth por clave interna, valida JPEG/PNG, guarda en «RX» del paciente por num_historia, es
idempotente y no cruza centros."""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from application.services import multimedia_service
from domain.config.settings import settings
from domain.models.core import Paciente

URL = "/radiologia/importar-romexis-interno"
JPG = b"\xff\xd8\xff\xe0" + b"x" * 200


@pytest.fixture
def cli(client, monkeypatch, tmp_path):
    monkeypatch.setattr(multimedia_service, "MEDIA_PAC", tmp_path)
    monkeypatch.setattr(settings, "internal_api_key", "k-test")
    return client


def _pac(session: Session, nh="4134"):
    p = Paciente(centro_id=1, num_historia=nh, nombre="Juan", apellidos="Manzanedo", activo=True)
    session.add(p); session.commit()


def _h(nh="4134", nombre="I1.jpg", key="k-test"):
    return {"X-Internal-Key": key, "X-Num-Historia": nh, "X-Filename": nombre}


def test_sin_clave_401(cli, session):
    assert cli.post(URL, content=JPG, headers=_h(key="mala")).status_code == 401


def test_guarda_en_rx_y_es_idempotente(cli, session, tmp_path):
    _pac(session)
    r = cli.post(URL, content=JPG, headers=_h())
    assert r.status_code == 200 and r.json()["estado"] == "guardada"
    ficheros = list(tmp_path.glob("4134*/RX/I1.jpg"))
    assert len(ficheros) == 1 and ficheros[0].read_bytes() == JPG
    r2 = cli.post(URL, content=b"\xff\xd8\xff" + b"y" * 50, headers=_h())
    assert r2.json()["estado"] == "ya_existe" and ficheros[0].read_bytes() == JPG


def test_rechaza_no_imagen_y_paciente_inexistente(cli, session):
    _pac(session)
    assert cli.post(URL, content=b"no soy imagen", headers=_h()).status_code == 415
    assert cli.post(URL, content=JPG, headers=_h(nh="999999")).status_code == 404
    assert cli.post(URL, content=JPG, headers=_h(nombre="../../x.jpg")).status_code in (200, 404)


def test_nombre_con_ruta_no_escapa(cli, session, tmp_path):
    _pac(session)
    cli.post(URL, content=JPG, headers=_h(nombre="../../evil.jpg"))
    assert not (tmp_path.parent / "evil.jpg").exists()
    assert not list(tmp_path.glob("../evil.jpg"))
