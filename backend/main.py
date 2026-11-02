"""Punto de entrada de la API FastAPI — MakingSmilesClinic."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import application.services.cita_reglas  # noqa: F401  (registra eventos before_insert/before_update de Cita)
from sqlmodel import Session
from infrastructure.config.db import engine, init_db
from infrastructure.realtime import bus
from infrastructure.debounce import debouncer
from infrastructure.scheduler import iniciar_scheduler, parar_scheduler
from infrastructure.seed import seed_dev
import asyncio

from api.geo_router import router as geo_router
from api.auth_router import router as auth_router
from api.paciente_auth_router import router as paciente_auth_router
from api.app_paciente_router import router as app_paciente_router
from api.app_doctor_router import router as app_doctor_router
from api.config_router import router as config_router
from api.configuracion_centro_router import router as configuracion_centro_router
from api.configuracion_agenda_router import router as configuracion_agenda_router
from api.agenda_router import router as agenda_router
from api.configuracion_staff_router import router as configuracion_staff_router
from api.configuracion_roles_router import router as configuracion_roles_router
from api.configuracion_admin_router import router as configuracion_admin_router
from api.pacientes_router import router as pacientes_router
from api.crm_router import router as crm_router
from api.presupuestos_router import router as presupuestos_router
from api.documentos_router import router as documentos_router
from api.superuser_router import router as superuser_router
from api.internal_tenant_router import router as internal_tenant_router
from api.clinico_router import router as clinico_router
from api.consulta_router import router as consulta_router
from api.comunicacion_router import router as comunicacion_router
from api.motion_router import router as motion_router
from api.voicebot_router import router as voicebot_router
from api.gestoria_router import router as gestoria_router
from api.gestor_ia_router import router as gestor_ia_router
from api.ws_router import router as ws_router
from api.informes_router import router as informes_router
from api.consentimientos_router import router as consentimientos_router
from api.casos_ortodoncia_router import router as casos_ortodoncia_router
from api.radiologia_router import router as radiologia_router
from api.dentia_router import router as dentia_router
from api.romexis_router import router as romexis_router
from api.cefalometria_router import router as cefalometria_router
from api.llm_router import router as llm_router
from api.ollama_relay_router import router as ollama_relay_router
from api.jarvis_operador_router import router as jarvis_operador_router
from api.chat_router import router as chat_router
from api.uploads_router import router as uploads_router
from api.media_router import router as media_router
from api.inicio_router import router as inicio_router
from api.agentes_db_router import router as agentes_db_router
from api.agentes_router import router as agentes_router
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
    # M00: base de datos, seed de desarrollo, bus de eventos (SSE) y scheduler.
    init_db()
    if settings.environment == "development" and settings.seed_dev:
        with Session(engine) as session:
            seed_dev(session)
    bus.bind_loop(asyncio.get_running_loop())
    await bus.connect()
    debouncer.bind_loop(asyncio.get_running_loop())
    iniciar_scheduler()
    yield
    parar_scheduler()
    await bus.aclose()


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
app.include_router(geo_router)
app.include_router(auth_router)
app.include_router(paciente_auth_router)
app.include_router(app_paciente_router)
app.include_router(app_doctor_router)
app.include_router(config_router)
app.include_router(configuracion_centro_router)
app.include_router(configuracion_agenda_router)
app.include_router(agenda_router)
app.include_router(configuracion_staff_router)
app.include_router(configuracion_roles_router)
app.include_router(configuracion_admin_router)
app.include_router(pacientes_router)
app.include_router(crm_router)
app.include_router(presupuestos_router)
app.include_router(documentos_router)
app.include_router(superuser_router)
app.include_router(internal_tenant_router)
app.include_router(clinico_router)
app.include_router(consulta_router)
app.include_router(comunicacion_router)
app.include_router(motion_router)
app.include_router(voicebot_router)
app.include_router(gestoria_router)
app.include_router(gestor_ia_router)
app.include_router(ws_router)
app.include_router(informes_router)
app.include_router(consentimientos_router)
app.include_router(casos_ortodoncia_router)
app.include_router(radiologia_router)
app.include_router(dentia_router)
app.include_router(romexis_router)
app.include_router(cefalometria_router)
app.include_router(llm_router)
app.include_router(ollama_relay_router)
app.include_router(jarvis_operador_router)
app.include_router(chat_router)
app.include_router(uploads_router)
app.include_router(media_router)
app.include_router(inicio_router)
app.include_router(agentes_db_router)
app.include_router(agentes_router)
app.include_router(health_router)


@app.get("/")
def root() -> dict:
    return {"service": "MakingSmilesClinic API", "docs": "/docs"}
