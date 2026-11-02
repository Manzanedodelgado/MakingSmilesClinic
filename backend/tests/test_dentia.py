"""DentIA: persistencia del análisis por imagen, validación, aislamiento por centro y mapeo de la IA."""
import pytest
from sqlmodel import Session

from api import dentia_router
from application.services import multimedia_service
from application.services.multimedia_service import MultimediaService
from domain.models.core import Centro, Paciente
from infrastructure.ia_dental_client import IaDentalNoDisponible

JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


def _paciente(session: Session, centro_id=1, nh="9001") -> Paciente:
    p = Paciente(centro_id=centro_id, num_historia=nh, nombre="Pilar", apellidos="Larrañaga", activo=True)
    session.add(p); session.commit(); session.refresh(p)
    return p


@pytest.fixture
def rx(session, monkeypatch, tmp_path):
    """Paciente con una radiografía en su carpeta RX → (paciente, file_id)."""
    monkeypatch.setattr(multimedia_service, "MEDIA_PAC", tmp_path)
    p = _paciente(session)
    svc = MultimediaService(session)
    (svc._carpeta_local(p, crear=True) / "RX").mkdir(parents=True, exist_ok=True)
    (svc._carpeta_local(p) / "RX" / "pano.jpg").write_bytes(JPG)
    return p, svc.listar(1, p)["radiografias"][0]["id"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def test_sin_analisis_devuelve_vacio(client, token, rx):
    p, fid = rx
    r = client.get(f"/pacientes/{p.id}/dentia", params={"file_id": fid}, headers=_h(token))
    assert r.status_code == 200 and r.json()["existe"] is False and r.json()["patrones"] == []


def test_guardar_y_recuperar(client, token, rx):
    p, fid = rx
    cuerpo = {"file_id": fid, "paso": 3,
              "patrones": [{"id": "a1", "categoria": "obturacion", "pieza": "46", "puntos": [[1, 2], [3, 4], [5, 6]]}],
              "plan": [{"patron_id": "a1", "tratamiento_id": 7, "tratamiento": "Obturación de composite",
                        "pieza": "46", "precio": 55}]}
    assert client.put(f"/pacientes/{p.id}/dentia", json=cuerpo, headers=_h(token)).status_code == 200
    got = client.get(f"/pacientes/{p.id}/dentia", params={"file_id": fid}, headers=_h(token)).json()
    assert got["existe"] and got["paso"] == 3
    assert got["patrones"][0]["categoria"] == "obturacion" and got["plan"][0]["precio"] == 55
    cuerpo["paso"] = 4                                           # upsert: no duplica la fila
    client.put(f"/pacientes/{p.id}/dentia", json=cuerpo, headers=_h(token))
    assert client.get(f"/pacientes/{p.id}/dentia", params={"file_id": fid}, headers=_h(token)).json()["paso"] == 4


def test_rechaza_categoria_desconocida_y_geometria_mala(client, token, rx):
    p, fid = rx
    mala = {"file_id": fid, "patrones": [{"id": "x", "categoria": "inventada"}]}
    assert client.put(f"/pacientes/{p.id}/dentia", json=mala, headers=_h(token)).status_code == 422
    punto = {"file_id": fid, "patrones": [{"id": "x", "categoria": "corona", "puntos": [[1, 2, 3]]}]}
    assert client.put(f"/pacientes/{p.id}/dentia", json=punto, headers=_h(token)).status_code == 422


def test_imagen_de_otro_paciente_o_inexistente_404(client, token, session, rx):
    p, fid = rx
    otro = _paciente(session, nh="9002")
    r = client.put(f"/pacientes/{otro.id}/dentia", json={"file_id": fid}, headers=_h(token))
    assert r.status_code == 404
    assert client.put(f"/pacientes/{p.id}/dentia", json={"file_id": "no-existe"}, headers=_h(token)).status_code == 404


def test_paciente_de_otro_centro_404(client, token, session, rx):
    c2 = Centro(nombre="Otro"); session.add(c2); session.commit(); session.refresh(c2)
    ajeno = _paciente(session, centro_id=c2.id, nh="9100")
    _, fid = rx
    assert client.get(f"/pacientes/{ajeno.id}/dentia", params={"file_id": fid}, headers=_h(token)).status_code == 404


def test_detectar_mapea_ia_sin_guardar(client, token, rx, monkeypatch):
    p, fid = rx
    ia = {"ancho": 100, "alto": 50, "aviso": "sugerencia",
          "dientes": [{"fdi": "18", "conf": 0.9, "bbox": [1, 2, 3, 4]}],
          "estructuras": [{"clase": "impactado", "conf": 0.8, "bbox": [0, 0, 5, 5], "fdi": "48",
                           "contornos": [[[0, 0], [5, 0], [5, 5]]]},
                          {"clase": "seno_maxilar", "conf": 0.7, "bbox": [0, 0, 1, 1], "fdi": None,
                           "contornos": [[[1, 1], [2, 2], [3, 1]]]},
                          {"clase": "otra_cosa", "conf": 0.5, "bbox": [0, 0, 1, 1], "fdi": None, "contornos": [[[1, 1]]]}],
          "errores": []}
    monkeypatch.setattr(dentia_router, "analizar_ortopantomografia", lambda b: ia)
    r = client.post(f"/pacientes/{p.id}/dentia/detectar", json={"file_id": fid}, headers=_h(token))
    assert r.status_code == 200
    cats = sorted(x["categoria"] for x in r.json()["patrones"])
    assert cats == ["incluido_impactado", "senos_maxilares"]
    assert all(x["origen"] == "ia" for x in r.json()["patrones"])
    assert r.json()["dientes"][0]["fdi"] == "18"
    assert client.get(f"/pacientes/{p.id}/dentia", params={"file_id": fid}, headers=_h(token)).json()["existe"] is False


def test_detectar_servicio_caido_503(client, token, rx, monkeypatch):
    p, fid = rx
    def caido(_): raise IaDentalNoDisponible("sin servicio")
    monkeypatch.setattr(dentia_router, "analizar_ortopantomografia", caido)
    assert client.post(f"/pacientes/{p.id}/dentia/detectar", json={"file_id": fid}, headers=_h(token)).status_code == 503
