"""Configuración central de la aplicación (capa de dominio)."""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_DEFAULT = "dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://makingsmiles:makingsmiles@localhost:5433/makingsmiles"
    )

    secret_key: str = _SECRET_DEFAULT
    environment: str = "development"

    # JWT
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12  # 12 h

    # Cookie de sesión: Secure exige HTTPS. En desarrollo va a False; fuera, se fuerza True.
    cookie_secure: bool = False

    # Seed de desarrollo (solo si environment == development).
    seed_dev: bool = True

    # URL canónica pública del frontend (enlaces de recuperación / consentimiento).
    public_frontend_url: str = "http://localhost:3000"

    # Freno al fuerza bruta en el login. 0 desactiva el freno.
    login_max_intentos: int = 5
    login_ventana_min: int = 15
    login_bloqueo_min: int = 15

    # OTP de la app del paciente (login por código, WhatsApp con fallback a email).
    otp_max_intentos: int = 5
    otp_ventana_min: int = 15
    otp_expira_min: int = 10
    # Token de la app nativa del paciente: vida larga (30 días), sin refresh en v1.
    paciente_token_expire_minutes: int = 60 * 24 * 30

    # Tiempo real (SSE): bus de eventos por Redis pub/sub. Vacío o Redis caído =>
    # fallback a memoria (dev local sin Redis sigue funcionando, con 1 worker).
    redis_url: str = ""

    # Relé de PLAN B para los operadores de OpenJarvis: con URL, Alex contesta a través
    # de su operador de Jarvis; vacío = Alex responde aquí. Clave compartida con Jarvis.
    jarvis_operador_url: str = ""
    jarvis_operador_key: str = ""

    # BBDD de PLATAFORMA (SuperUser): registro de centros, separada de la operativa de
    # cada centro. Vacío = misma instancia Postgres, BD distinta (la deriva compose).
    platform_database_url: str = ""
    # Clave compartida que exige el router interno (/internal/tenant/...) — único punto
    # por el que SuperUser toca datos operativos de un centro, nunca por acceso directo a BD.
    internal_api_key: str = "dev-internal-key-change-me"
    # Base URL del propio backend (self-call): SuperUser llama aquí, nunca hace queries directas.
    internal_api_base_url: str = "http://localhost:8000"

    @model_validator(mode="after")
    def _exigir_secreto_en_produccion(self):
        """Fuera de development, el JWT no puede firmarse con el secreto por defecto."""
        if self.environment.strip().lower() != "development":
            self.cookie_secure = True
            if not self.public_frontend_url.startswith("https://"):
                raise ValueError("PUBLIC_FRONTEND_URL debe usar HTTPS fuera de development")
            if self.secret_key == _SECRET_DEFAULT or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY inseguro para environment=%r: define un SECRET_KEY propio "
                    "de al menos 32 caracteres." % self.environment
                )
        return self


settings = Settings()
