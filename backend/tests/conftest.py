"""Fixtures de test: BD SQLite en memoria + cliente con sesión inyectada."""
import os

os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-32-characters-minimum-length-for-testing"
os.environ["DATABASE_URL"] = "sqlite://"

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
