"""Fixtures de test: BD SQLite en memoria + cliente con sesión inyectada."""
import os

os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-32-characters-minimum-length-for-testing"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["INTERNAL_API_KEY"] = "test-internal-api-key-32-chars-minimum-length"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import domain.models  # noqa: F401  (registra todas las tablas en la metadata)
from infrastructure.config.db import get_session
from infrastructure.seed import seed_dev
from main import app


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_dev(session)
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    # Sin context manager: NO disparamos el lifespan. La BD de test la crea el fixture.
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(name="token")
def token_fixture(client: TestClient) -> str:
    resp = client.post("/auth/login", json={
        "email": "admin@makingsmiles.local", "password": "admin1234",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─────────────── fixtures heredados del legado (paridad) ───────────────
@pytest.fixture(autouse=True)
def memoria_llm_fresca():
    """La memoria de rescate del LLM no debe filtrarse entre tests."""
    from infrastructure.external_apis.llm_client import reiniciar_memoria
    from infrastructure.llm.ollama_provider import reiniciar_proveedor_llm
    reiniciar_memoria()
    reiniciar_proveedor_llm()
    yield
    reiniciar_memoria()
    reiniciar_proveedor_llm()


# Módulos que PRUEBAN las reglas de cita: en ellos no se rellena nada.
_PRUEBAN_REGLAS_CITA = {"test_cita_reglas", "test_cita_id_cita", "test_soap_urgencia"}


@pytest.fixture(autouse=True)
def citas_de_prueba_completas(request):
    """Completa citas mínimas de otros tests ANTES de la regla cita_reglas."""
    if request.module.__name__.rsplit(".", 1)[-1] in _PRUEBAN_REGLAS_CITA:
        yield
        return
    from sqlalchemy import event, text
    from domain.models.core import Cita

    def _uno(conn, tabla: str, centro_id: int, nombre: str) -> int:
        fila = conn.execute(text(f"SELECT id FROM {tabla} WHERE centro_id = :c AND nombre = :n "
                                 "ORDER BY id LIMIT 1"), {"c": centro_id, "n": nombre}).first()
        if fila:
            return fila[0]
        conn.execute(text(f"INSERT INTO {tabla} (centro_id, nombre, activo, created_at, updated_at) "
                          "VALUES (:c, :n, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
                     {"c": centro_id, "n": nombre})
        return conn.execute(text(f"SELECT id FROM {tabla} WHERE centro_id = :c AND nombre = :n "
                                 "ORDER BY id DESC LIMIT 1"), {"c": centro_id, "n": nombre}).first()[0]

    def _completar(_mapper, conn, cita):
        if cita.gabinete_id is None:
            cita.gabinete_id = _uno(conn, "gabinetes", cita.centro_id, "Box de prueba")
        if cita.tipo_cita_id is None:
            cita.tipo_cita_id = _uno(conn, "tipos_cita", cita.centro_id, "Tipo de prueba")
        if cita.duracion_min is None:
            cita.duracion_min = 30
        ficha = (conn.execute(text("SELECT nombre, apellidos, coalesce(telefono_movil, telefono_fijo) "
                                   "FROM pacientes WHERE id = :p"), {"p": cita.paciente_id}).first()
                 if cita.paciente_id else None) or (None, None, None)
        if not cita.telefono_movil and not ficha[2]:
            cita.telefono_movil = "600000000"
        if not cita.nombre and not ficha[0]:
            cita.nombre = "Prueba"
        if not cita.apellidos and not ficha[1]:
            cita.apellidos = "De Test"

    event.listen(Cita, "before_insert", _completar, insert=True)
    yield
    event.remove(Cita, "before_insert", _completar)
