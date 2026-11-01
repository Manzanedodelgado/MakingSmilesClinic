"""Tests de M01: login OTP de la app del paciente (canal email; WhatsApp es M12)."""
import hashlib
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from domain.models.core import Centro, Paciente, PacienteOtp


def _crear_paciente(session: Session, **kw) -> Paciente:
    centro_id = session.exec(select(Centro.id)).first()
    p = Paciente(centro_id=centro_id, activo=True, **kw)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_solicitar_codigo_inexistente_es_silencioso(client: TestClient):
    # Anti-enumeración: respuesta idéntica aunque el identificador no exista.
    r = client.post("/app/auth/solicitar-codigo", json={"identificador": "noexiste@test.local"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_verificar_codigo_email_valido(client: TestClient, session: Session):
    p = _crear_paciente(session, nombre="Paciente", apellidos="Prueba", email="pac@test.local")
    codigo = "123456"
    session.add(PacienteOtp(
        paciente_id=p.id, centro_id=p.centro_id,
        codigo_hash=hashlib.sha256(codigo.encode()).hexdigest(),
        canal="email", expira_at=datetime.utcnow() + timedelta(minutes=10),
    ))
    session.commit()

    r = client.post("/app/auth/verificar-codigo", json={
        "identificador": "pac@test.local", "codigo": codigo,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["paciente"]["id"] == p.id


def test_verificar_codigo_invalido_da_401(client: TestClient, session: Session):
    _crear_paciente(session, nombre="Paciente", email="pac2@test.local")
    r = client.post("/app/auth/verificar-codigo", json={
        "identificador": "pac2@test.local", "codigo": "000000",
    })
    assert r.status_code == 401
