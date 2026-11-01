"""Configuración de base de datos e inicialización del engine (infraestructura)."""
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from domain.config.settings import settings

engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)


def init_db() -> None:
    """Crea las tablas declaradas con SQLModel si no existen."""
    import domain.models  # noqa: F401  (registra los modelos en metadata)

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Dependencia FastAPI: entrega una sesión de DB por request."""
    with Session(engine) as session:
        yield session
