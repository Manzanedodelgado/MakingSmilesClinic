"""Configuración central de la aplicación (capa de dominio)."""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_DEFAULT = "dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://makingsmiles:makingsmiles@localhost:5433/makingsmiles"
    
    # LLM Provider Configuration
    llm_provider: str = "ollama"
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5-coder:7b"
    ollama_timeout: float = 40.0
    ollama_retries: int = 4

    # RESCATE cuando Ollama no está operativo (la WiFi de este servidor no siempre
    # llega al Ollama de pc-escaner, y esa máquina puede estar apagada). Cadena de
    # proveedores GRATUITOS compatibles con la API de OpenAI, en orden de preferencia
    # — el primero con API key puesta que responda gana; si todos fallan, se devuelve
    # el error del último. Modelos verificados con llamada real el 14-oct-2026
    # (se descarta lo roto de rondas anteriores): devuelven contenido de verdad y
    # tool_calls, no solo un 200 vacío.
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # gpt-oss-120b se quedó sin cuota diaria (RPD 1000/1000) el día de la verificación;
    # qwen3.8-27b responde en 0,17 s con presupuesto propio y con tools.
    groq_model: str = "qwen/qwen3.8-27b"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # nemotron-3-super:free se descarta como respaldo: se gasta TODO el max_tokens en
    # "pensar" y devuelve content vacío (los agentes recibirían un mensaje en blanco).
    # lightning es rápido, con tools y devuelve contenido (verificado 14-oct-2026).
    openrouter_model: str = "nvidia/nemotron-3.5-lightning:free"

    # Cerebras DESCARTADO: la cuenta de estas claves da 402 "Payment required" en los
    # DOS únicos modelos que lista (verificado 14-oct-2026: no es un nombre de modelo
    # mal puesto — es la cuenta entera sin billing). Tercer rescate = Gemini gratis
    # vía su endpoint compatible con OpenAI (probado con llamada real: contenido y
    # tool_calls correctos). gemini-3.6-flash estaba sin cuota; 2.5-flash responde.
    gemini_api_key_free: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model_free: str = "gemini-2.5-flash"
    # Gemini gratis y OpenRouter ":free" pueden entrenar con lo que reciben: fuera del
    # rescate de los agentes salvo que se active a propósito (ver ollama_provider).
    rescate_nube_que_entrena: bool = False

    # Relé de PLAN B para los operadores de OpenJarvis (api/ollama_relay_router.py):
    # token que va en la ruta /ollama/<token>/api/… y sin el que el relé responde 404
    # (no anuncia que exista). Vacío = relé desactivado. OpenJarvis solo habla la API
    # nativa de Ollama contra UNA URL, así que esa URL es este relé.
    ollama_relay_token: str = ""
    # Ruta de WhatsApp por Jarvis (.91): con URL, Alex contesta a través de su operador de
    # Jarvis, que piensa con qwen3.5-clinica y pide los datos a esta web por /internal/jarvis
    # (las reglas y la verificación de identidad siguen aquí). Vacío = Alex contesta aquí.
    jarvis_operador_url: str = ""
    jarvis_operador_key: str = ""
    # BBDD de PLATAFORMA (SuperUser): registro de centros, separada de la operativa de cada
    # centro (pacientes/citas/personal). Por defecto, misma instancia Postgres, BD distinta.
    platform_database_url: str = ""
    # Clave compartida que exige el router interno (/internal/tenant/...) — el único punto por
    # el que SuperUser puede tocar datos operativos de un centro, nunca por acceso directo a BD.
    internal_api_key: str = "dev-internal-key-change-me"
    # Base URL del propio backend (self-call): SuperUser llama aquí, nunca hace queries directas.
    internal_api_base_url: str = "http://localhost:8000"
    secret_key: str = "dev-secret-change-me"
    environment: str = "development"
    # Deja leer /openapi.json en producción (sin activar /docs ni /redoc) para que un
    # agente externo (Jarvis/Hermes) pueda mapear la API sin exponer la UI de Swagger.
    enable_ai_openapi: bool = False

    # CENTINELA — JWT
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12  # 12 h

    # Seed de desarrollo (solo si environment == development)
    seed_dev: bool = True

    # URL canónica pública para enlaces de recuperación y consentimiento.
    public_frontend_url: str = "http://localhost:3000"

    # Automatización de comunicación: arranca el scheduler (el envío real lo gatea
    # además `automatizacion_activa` en la integración WhatsApp de cada centro).
    scheduler_enabled: bool = True

    # Cookie de sesión: el atributo Secure exige HTTPS. En desarrollo (HTTP puro por
    # LAN/Tailscale) va a False; en cualquier otro entorno se fuerza a True.
    cookie_secure: bool = False

    # Tiempo real (SSE): bus de eventos por Redis pub/sub. Sustituye al bus en
    # memoria (que solo servia con 1 worker uvicorn). Vacio o Redis caido => fallback
    # a memoria (dev local sin Redis sigue funcionando, con la limitacion de 1 worker).
    redis_url: str = ""

    # Centinela/Victor: reiniciar contenedores conocidos (p.ej. Evolution/WhatsApp zombi)
    # sin dar al backend acceso directo al socket de Docker (privilegios de root sobre el
    # host). Habla por TCP interno con un docker-socket-proxy (Tecnativa) que SOLO expone
    # start/stop/restart/kill de contenedores — ver docker-compose.yml / docker_client.py.
    docker_proxy_url: str = "http://docker-proxy:2375"

    # COPIAS DE SEGURIDAD (Centinela). Programadas a las 15:00 y 22:00, L-V.
    # `backup_destino` es una ruta rsync FUERA de este servidor — una copia guardada en la
    # misma máquina que los datos no protege del fallo que más importa (disco, borrado,
    # ransomware). Vacío = solo copia local, y Centinela avisa en cada ejecución.
    backup_dir: str = "/backups"
    backup_media_dir: str = "/app/media"
    # Configuración del servidor (montada en solo lectura): secretos, Caddyfile,
    # unidades de systemd y Orthanc. Es lo que convierte la copia en reconstruible.
    backup_servidor_dir: str = "/servidor"
    backup_destino: str = ""          # p.ej. "usuario@100.81.242.87:/ruta/MakingSmiles"
    backup_ssh_key: str = ""          # clave privada para el envío (sin contraseña interactiva)
    backup_retencion_copias: int = 14  # 7 días a 2 copias/día

    # Web que ve la clínica (build de producción bajo systemd en el host, :3000).
    # Vacío = se resuelve sola la IP del anfitrión (infrastructure/host_net.py).
    # Centinela la vigila desde fuera, como lo haría un paciente con el navegador.
    frontend_health_url: str = ""
    # Servidor de IA de nervio/seno (OralGPT) en pc-escaner, vía Tailscale: su /health lo vigila Centinela. Vacío = no se vigila.
    oralgpt_health_url: str = ""
    frontend_puerto: int = 3000

    # Freno al fuerza bruta en el login (C7). Umbral de intentos fallidos por email
    # dentro de la ventana → bloqueo temporal. 0 desactiva el freno.
    login_max_intentos: int = 5
    login_ventana_min: int = 15
    login_bloqueo_min: int = 15
    # Umbrales de DETECCIÓN (objetivo `autenticacion` de Centinela) — emails distintos
    # fallando desde una misma IP en 15 min. Nunca bloquean nada, solo alertan.
    login_alerta_ip_emails_distintos_warn: int = 8
    login_alerta_ip_emails_distintos_error: int = 20

    # OTP de la app del paciente (login por código, WhatsApp con fallback a email).
    otp_max_intentos: int = 5
    otp_ventana_min: int = 15
    otp_expira_min: int = 10
    # Token de la app nativa del paciente: sin flujo de refresh en v1, vida larga (30 días)
    # para no forzar re-OTP constante — decisión explícita, no un descuido.
    paciente_token_expire_minutes: int = 60 * 24 * 30

    @model_validator(mode="after")
    def _exigir_secreto_en_produccion(self):
        """C7: en cualquier entorno que NO sea desarrollo, el JWT NO puede firmarse con el
        secreto por defecto ni con uno corto (sería forjable). Fallo RUIDOSO en el arranque:
        obliga a exportar un SECRET_KEY propio de ≥32 chars antes de desplegar."""
        if self.environment.strip().lower() != "development":
            self.cookie_secure = True
            if not self.public_frontend_url.startswith("https://"):
                raise ValueError("PUBLIC_FRONTEND_URL debe usar HTTPS fuera de development")
            if self.secret_key == _SECRET_DEFAULT or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY inseguro para environment='%s': define un SECRET_KEY propio "
                    "de al menos 32 caracteres (nunca el default '%s'). El seed_dev y las "
                    "credenciales de demo tampoco se crean fuera de development."
                    % (self.environment, _SECRET_DEFAULT)
                )
            if self.internal_api_key == "dev-internal-key-change-me" or len(self.internal_api_key) < 32:
                raise ValueError(
                    "INTERNAL_API_KEY inseguro para environment='%s': define uno propio de "
                    "al menos 32 caracteres — protege el router interno de tenant." % self.environment
                )
        return self


settings = Settings()
