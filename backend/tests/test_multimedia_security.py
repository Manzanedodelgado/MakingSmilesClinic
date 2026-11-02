"""Regresión de seguridad de multimedia_service (fase SERVICES, prioridad WRITE>READ).

H-1 (ALTO): el filesystem local agrupa carpetas por num_historia SIN centro
(_carpeta_local). romexis_router._siguiente_num_historia genera num_historia POR
CENTRO (y su check de duplicado es por centro), así que dos centros pueden tener
pacientes con el MISMO nh: listar/media del paciente del centro A devolvían —y
guardar_foto_paciente escribía en— las fotos/RX del paciente del centro B
(fuga de datos clínicos cross-tenant). Fix: guard anti-ambigüedad — si el nh
existe en >1 centro, la fuente local se desactiva (fail-closed) para ese nh.

H-2 (MEDIO): subir_a_drive recibía centro_id y paciente sin validar que el
paciente perteneciera a ese centro. Fix: return None (best-effort, nunca rompe
la subida original) si pac.centro_id != centro_id.

H-3 (BAJO): subcarpeta no se sanitizaba con _safe() (asimetría con nombre).
"""
import pytest
from sqlmodel import Session, select

from application.services import multimedia_service
from application.services.multimedia_service import MultimediaService
from domain.models.core import Centro, Paciente
from infrastructure.external_apis import drive_client


def _pac(session: Session, centro_id: int, nh: str) -> Paciente:
    p = Paciente(centro_id=centro_id, num_historia=nh, nombre="Nombre",
                 apellidos=f"Ape{centro_id}", activo=True)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _pac_del_centro(session: Session, centro_id: int, nh: str) -> Paciente:
    return session.exec(select(Paciente).where(
        Paciente.centro_id == centro_id, Paciente.num_historia == nh)).first()


# ───────────── H-1: filesystem local no cruza centros ─────────────

def test_carpeta_local_none_si_nh_en_varios_centros(session, tmp_path, monkeypatch):
    """nh duplicado entre centros → fuente local desactivada (fail-closed)."""
    monkeypatch.setattr(multimedia_service, "MEDIA_PAC", tmp_path)
    c2 = Centro(nombre="Centro 2")
    session.add(c2)
    session.commit()
    session.refresh(c2)
    _pac(session, 1, "7")
    _pac(session, c2.id, "7")
    # La carpeta FS la "dejó" el paciente del centro 2 (otro centro, mismo nh).
    carpeta_otro = tmp_path / "7 — Ape2, Nombre"
    carpeta_otro.mkdir()
    (carpeta_otro / "rx.jpg").write_bytes(b"del-otro-centro")
    mm = MultimediaService(session)
    pac1 = _pac_del_centro(session, 1, "7")
    assert mm._carpeta_local(pac1) is None
    out = mm.listar(1, pac1)
    assert out["fotos"] == [] and out["radiografias"] == []


def test_listar_nh_unico_sigue_funcionando(session, tmp_path, monkeypatch):
    """El guard H-1 no rompe el caso normal (nh único): la carpeta se encuentra y se lista."""
    monkeypatch.setattr(multimedia_service, "MEDIA_PAC", tmp_path)
    _pac(session, 1, "7")
    carpeta = tmp_path / "7 — Ape1, Nombre"
    carpeta.mkdir()
    (carpeta / "foto.jpg").write_bytes(b"contenido")
    mm = MultimediaService(session)
    pac1 = _pac_del_centro(session, 1, "7")
    assert mm._carpeta_local(pac1) == carpeta
    out = mm.listar(1, pac1)
    assert [f["name"] for f in out["fotos"]] == ["foto.jpg"]


# ───────────── H-2: subir_a_drive valida paciente↔centro ─────────────

def test_subir_a_drive_rechaza_paciente_de_otro_centro(session, monkeypatch):
    """Defensa en profundidad: pac de otro centro → None, sin tocar Drive.
    El paciente correcto SÍ llega a Drive (el guard no rompe el caso válido)."""
    _pac(session, 1, "1")
    pac_otro = Paciente(centro_id=99, num_historia="1", nombre="X", apellidos="Y", activo=True)
    session.add(pac_otro)
    session.commit()
    session.refresh(pac_otro)
    subidas = []
    monkeypatch.setattr(drive_client, "buscar_subcarpeta_prefijo",
                        lambda cfg, root, pref: "folderX")
    monkeypatch.setattr(drive_client, "buscar_o_crear_carpeta",
                        lambda cfg, name, parent: "subX")
    monkeypatch.setattr(drive_client, "subir",
                        lambda cfg, **kw: subidas.append(kw) or {"id": "file1"})
    mm = MultimediaService(session)
    # cfg completo: sin "carpetas.pacientes" el rechazo pasaría trivialmente
    # (no habría carpeta destino) y no probaría el guard.
    monkeypatch.setattr(mm, "_drive_cfg",
                        lambda cid: {"api_key": "k", "carpetas": {"pacientes": "rootFolder"}})
    assert mm.subir_a_drive(1, pac_otro, b"x", "foto.jpg") is None
    assert subidas == []
    pac_ok = _pac_del_centro(session, 1, "1")
    assert mm.subir_a_drive(1, pac_ok, b"x", "foto.jpg") == "file1"
    assert len(subidas) == 1 and subidas[0]["folder_id"] == "subX"


# ───────────── H-3: subcarpeta sanitizada ─────────────

def test_guardar_foto_subcarpeta_no_escapa(session, tmp_path, monkeypatch):
    """subcarpeta '../escape' NO debe escribir fuera de la carpeta del paciente."""
    monkeypatch.setattr(multimedia_service, "MEDIA_PAC", tmp_path)
    _pac(session, 1, "5")
    mm = MultimediaService(session)
    pac = _pac_del_centro(session, 1, "5")
    dest = mm.guardar_foto_paciente(1, pac, b"x", "foto.jpg", subcarpeta="../escape")
    assert dest is not None
    base = tmp_path / "5 — Ape1, Nombre"   # etiqueta real: {nh} — {apellidos}, {nombre}
    assert base.resolve() in dest.resolve().parents
    assert not (tmp_path / "escape").exists()


# ───────────── guard preexistente: anti-traversal ─────────────

def test_media_local_anti_traversal(session, tmp_path, monkeypatch):
    """El fichero pedido debe estar dentro de la carpeta del paciente (regresión del guard)."""
    monkeypatch.setattr(multimedia_service, "MEDIA_PAC", tmp_path)
    _pac(session, 1, "9")
    (tmp_path / "9 — Ape1, Nombre").mkdir()
    mm = MultimediaService(session)
    pac = _pac_del_centro(session, 1, "9")
    enc = multimedia_service._enc("../../secreto.jpg")
    assert mm._media_local(pac, enc) is None
