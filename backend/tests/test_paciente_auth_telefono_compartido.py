"""Login paciente con teléfono compartido: el nombre se exige ANTES de enviar.
Regla: mismo teléfono en varios pacientes → sin nombre+apellidos no sale código (428);
con nombre que identifica a uno solo → código solo para él (una fila OTP)."""
import re

import pytest
from sqlmodel import Session, select

from application.services.comunicacion_service import ComunicacionService
from domain.models.core import Paciente
from domain.models.core import PacienteOtp

TEL = "600111222"


@pytest.fixture(autouse=True)
def _regexp_replace_sqlite(session: Session):
    # Postgres en prod, SQLite en tests: registra regexp_replace(source, pat, rep, flags).
    raw = session.get_bind().raw_connection()
    raw.create_function("regexp_replace", 4,
                        lambda s, pat, rep, flags: re.sub(pat, rep, s or ""))
    raw.create_function("right", 2, lambda s, n: (s or "")[-int(n):])
    yield


def _pac(session: Session, nombre: str, apellidos: str, *, whatsapp: bool = True) -> Paciente:
    p = Paciente(centro_id=1, nombre=nombre, apellidos=apellidos, activo=True,
                 telefono_movil=TEL, acepta_whatsapp=whatsapp)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _otps(session: Session, pid: int):
    return session.exec(select(PacienteOtp).where(
        PacienteOtp.paciente_id == pid, PacienteOtp.usado_at.is_(None))).all()


def test_telefono_compartido_exige_nombre_antes_de_enviar(session: Session, client, monkeypatch):
    _pac(session, "Ana", "García López")
    _pac(session, "Luis", "García López")
    enviados = []
    monkeypatch.setattr(ComunicacionService, "enviar_texto",
                        lambda self, c, t, m: enviados.append((c, t, m)) or True)

    r = client.post("/app/auth/solicitar-codigo", json={"identificador": TEL})
    assert r.status_code == 428, r.text
    assert enviados == []  # sin nombre no sale ningún código

    r = client.post("/app/auth/solicitar-codigo",
                    json={"identificador": TEL, "nombre_apellidos": "Alguien Otro"})
    assert r.status_code == 428, r.text
    assert enviados == []

    r = client.post("/app/auth/solicitar-codigo",
                    json={"identificador": TEL, "nombre_apellidos": "Luis García"})
    assert r.status_code == 200, r.text
    assert len(enviados) == 1  # un solo envío, al teléfono identificado


def test_codigo_solo_para_el_paciente_identificado(session: Session, client, monkeypatch):
    ana = _pac(session, "Ana", "García López")
    luis = _pac(session, "Luis", "García López")
    monkeypatch.setattr(ComunicacionService, "enviar_texto", lambda self, c, t, m: True)

    r = client.post("/app/auth/solicitar-codigo",
                    json={"identificador": TEL, "nombre_apellidos": "Ana Garcia"})
    assert r.status_code == 200, r.text
    assert len(_otps(session, ana.id)) == 1
    assert _otps(session, luis.id) == []  # Luis no recibe nada


def test_telefono_unico_no_pide_nombre(session: Session, client, monkeypatch):
    _pac(session, "Sola", "Pérez Ruiz")
    monkeypatch.setattr(ComunicacionService, "enviar_texto", lambda self, c, t, m: True)
    r = client.post("/app/auth/solicitar-codigo", json={"identificador": TEL})
    assert r.status_code == 200, r.text
