"""BBDD de PLATAFORMA — registro de centros para SuperUser. Físicamente separada de la
BBDD operativa (pacientes/citas/personal de cada centro): motor propio, sin metadata ORM
compartida con `domain.models`. El acceso a datos operativos NUNCA pasa por aquí — solo
por el router interno (`api/internal_tenant_router.py`)."""
from collections.abc import Generator

from sqlmodel import Session, create_engine

from domain.config.settings import settings


def _platform_url() -> str:
    if settings.platform_database_url:
        return settings.platform_database_url
    # SQLite (tests) no tiene "otra BD en la misma instancia": derivar una ruta con
    # rpartition produce `sqlite://makingsmiles_platform`, que es una URL inválida y
    # rompía al IMPORTAR el módulo. En ese caso se comparte la misma URL.
    if settings.database_url.startswith("sqlite"):
        return settings.database_url
    # Misma instancia Postgres, BD distinta (basta con no compartir tablas/esquema).
    root, _, _ = settings.database_url.rpartition("/")
    return f"{root}/makingsmiles_platform"


# Perezoso: crear el engine al importar hacía que un DATABASE_URL no-Postgres tumbara
# la importación del módulo (y con ella toda la suite).
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(_platform_url(), echo=False, pool_pre_ping=True)
    return _engine


class _EnginePerezoso:
    """Mantiene `platform_engine` como nombre público sin crearlo hasta el primer uso."""

    def __getattr__(self, nombre):
        return getattr(_get_engine(), nombre)


platform_engine = _EnginePerezoso()


def get_platform_session() -> Generator[Session, None, None]:
    with Session(_get_engine()) as session:
        yield session
