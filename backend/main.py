"""Punto de entrada de la API FastAPI — MakingSmilesClinic."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth_router import router as auth_router
from api.paciente_auth_router import router as paciente_auth_router
from api.config_router import router as config_router
from api.configuracion_centro_router import router as configuracion_centro_router
from api.configuracion_agenda_router import router as configuracion_agenda_router
from api.configuracion_staff_router import router as configuracion_staff_router
from api.configuracion_roles_router import router as configuracion_roles_router
from api.uploads_router import router as uploads_router
from api.health_router import router as health_router
from domain.config.settings import settings

# CORS. En producción el navegador NUNCA llama al backend directamente (va por el
# rewrite /api/* de Next en Vercel), así que solo se permite el dominio público.
if settings.environment.strip().lower() == "development":
    ALLOWED_ORIGINS = [
        *[f"http://localhost:{port}" for port in range(3000, 3007)],
        *[f"http://127.0.0.1:{port}" for port in range(3000, 3007)],
    ]
else:
    ALLOWED_ORIGINS = [settings.public_frontend_url]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # M00 añadirá init_db/seed, bus de eventos, scheduler y vigilancia.
    # El esqueleto no arranca servicios externos: importar main:app no toca BD ni Redis.
    yield


def _api_docs_options(environment: str) -> dict:
    if environment.strip().lower() == "development":
        return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
    # Producción: Swagger/Redoc siempre ocultos.
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


app = FastAPI(
    title="MakingSmilesClinic API",
    version="0.1.0",
    lifespan=lifespan,
    **_api_docs_options(settings.environment),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Orden de inclusión = precedencia del legado (main.py del sistema original).
app.include_router(auth_router)
app.include_router(paciente_auth_router)
app.include_router(config_router)
app.include_router(configuracion_centro_router)
app.include_router(configuracion_agenda_router)
app.include_router(configuracion_staff_router)
app.include_router(configuracion_roles_router)
app.include_router(uploads_router)
app.include_router(health_router)


@app.get("/")
def root() -> dict:
    return {"service": "MakingSmilesClinic API", "docs": "/docs"}
