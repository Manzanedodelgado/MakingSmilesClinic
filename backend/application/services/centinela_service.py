"""🛡️ CENTINELA + Centinela — salud REAL de la instalación: detecta, repara si puede, y solo
avisa cuando no puede. Extraído de `api/superuser_router.py::centinela()` para que tanto el
panel manual (GET /superuser/centinela) como el tick programado (infrastructure/scheduler.py)
llamen exactamente a la misma lógica — nunca duplicada.

Filosofía de cada objetivo vigilado: comprobar de VERDAD (no solo "existe una fila activa"),
reparar de forma autónoma cuando hay una acción segura y conocida, y rendirse (avisar) solo
cuando la reparación no basta o no existe. Todo queda en `Auditoria` — incluida una entrada
diaria aunque no pase nada (ver `_registrar_bitacora`).
"""
import shutil
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlmodel import Session, select

from application.services.auth_service import AuthService
from application.services.config_service import ConfigService
from application.services.comunicacion_service import ComunicacionService
from domain.config.settings import settings
from domain.models.auditoria import Auditoria
from domain.models.config import Integracion
from infrastructure import disco_seguro, jobs_heartbeat, whatsapp_monitor
from infrastructure.docker_client import DockerError, restart_contenedor
from infrastructure.error_monitor import errores_recientes
from infrastructure.external_apis.evolution_api import EvolutionClient, EvolutionError
from infrastructure.mailer import send_email
from infrastructure.mailer import test_connection as smtp_test
from infrastructure.external_apis.gmail_imap import test_connection as imap_test
from infrastructure.external_apis.orthanc_client import ping as orthanc_ping
from infrastructure.external_apis import drive_client

_INTEGR_LABEL = {"orthanc": "Orthanc (DICOM/RX)", "whatsapp": "WhatsApp (Evolution)",
                 "email_saliente": "Email saliente (SMTP)", "email_imap": "Email entrante (IMAP)",
                 "llm": "IA / LLM", "google_drive": "Google Drive (multimedia)"}

# Escalada de reparación de WhatsApp — constantes de código, no configurables desde el
# panel (son parámetros de bajo nivel que un no-técnico no debería tocar).
UMBRAL_FALLOS_WHATSAPP = 2      # fallos reales de envío en 15 min para considerarlo "mal" (28-29 oct-2026: con 3
#                                  y un usuario que reintenta una vez, Evolution quedaba en 500 horas sin reparar)
UMBRAL_FALLOS_TRAS_REPARAR = 1   # ya reparado una vez: UN solo fallo nuevo basta para escalar
ESPERA_SOFT_SEG = 30             # tras instance_restart, antes de escalar a docker_restart
ESPERA_DOCKER_SEG = 75           # tras docker_restart, antes de rendirse y alertar
ESPERA_REINTENTO_SEG = 15 * 60   # tras "agotado", antes de reintentar desde cero

# Ruta de la app del paciente usada como sonda: exige token, así que sin credenciales debe
# responder 401. Si cambia el prefijo de la app, cambiarla aquí.
RUTA_SONDA_APP = "/app/pacientes/me/perfil"

_CONECTORES_NUEVOS = ("whatsapp", "email_saliente", "email_imap", "orthanc", "google_drive")
_RANGO_NIVEL = {"ok": 0, "warn": 1, "error": 2}
_RANGO_SEVERIDAD = {"info": 0, "warning": 1, "critical": 2}

# Bitácora sin volumen desproporcionado (§6 del plan): contador de ticks omitidos desde la
# última fila realmente escrita, en memoria — perderlo en un reload solo hace que el próximo
# contador empiece de 0, nunca oculta una transición real (esa SIEMPRE se escribe).
_ticks_desde_ultimo: dict[int, int] = {}


def _migrar_objetivos(objetivos: dict) -> dict:
    """Retrocompat: si una instalación ya tenía `conectores` guardado explícitamente (p.ej.
    `false`), propagar ese valor como default de las claves nuevas de conector en vez de
    perder esa intención por el default `True` de una clave ausente."""
    if "conectores" in objetivos:
        legado = objetivos["conectores"]
        for k in _CONECTORES_NUEVOS:
            objetivos.setdefault(k, legado)
    return objetivos


class CentinelaService:
    def __init__(self, session: Session):
        self.session = session

    def ejecutar(self, centro_id: int, *, origen: str = "manual",
                 usuario_id: Optional[int] = None, ip: Optional[str] = None) -> dict:
        session = self.session

        def audit(accion: str, recurso: Optional[str] = None, detalle=None, exito: bool = True) -> None:
            try:
                AuthService(session).audit(accion, usuario_id=usuario_id, centro_id=centro_id,
                                           recurso=recurso, detalle=detalle, ip=ip, exito=exito)
            except Exception:  # raiz: vigilancia: un fallo de sonda no tumba el resto del tick; se registra
                session.rollback()

        cfg = ConfigService(session).resolve("centinela.config", centro_id=centro_id,
                                              sistema="centinela", default=None) or {}
        if cfg and not cfg.get("activa", True):
            return {"nivel": "off", "activa": False, "sistema": [], "integraciones": [],
                    "alertaDisparada": False, "comprobado": datetime.now().isoformat(timespec="seconds")}

        objetivos = _migrar_objetivos(dict((cfg.get("vigilancia") or {}).get("objetivos") or {}))
        vigila = lambda k: objetivos.get(k, True)  # noqa: E731
        modo_accion = (cfg.get("permisos") or {}).get("modo_accion")
        remediacion = modo_accion == "remediacion"

        sistema: list[dict] = []

        # ── Base de datos ──
        if vigila("base_datos"):
            try:
                session.exec(text("SELECT 1")).one()
                size = session.exec(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).one()[0]
                conex = int(session.exec(text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()")).one()[0])
                sistema.append({"clave": "db", "label": "Base de datos", "estado": "ok",
                                "detalle": f"{size} · {conex} conexiones"})
            except Exception as e:  # raiz: vigilancia: un fallo de sonda no tumba el resto del tick; se registra
                sistema.append({"clave": "db", "label": "Base de datos", "estado": "error", "detalle": str(e)[:120]})

        # ── Estadísticas de la BD (ANALYZE) ──
        if vigila("estadisticas_bd"):
            try:
                stale = session.exec(text(
                    "SELECT relname FROM pg_stat_user_tables WHERE last_analyze IS NULL "
                    "AND last_autoanalyze IS NULL AND pg_total_relation_size(relid) > 1048576 "
                    "ORDER BY pg_total_relation_size(relid) DESC")).all()
                nombres = [r[0] for r in stale]
                if not nombres:
                    sistema.append({"clave": "stats_bd", "label": "Estadísticas de la BD", "estado": "ok", "detalle": "Al día"})
                else:
                    estado = "warn"
                    detalle = f"{len(nombres)} tabla(s) sin analizar nunca: {', '.join(nombres[:5])}" + (" …" if len(nombres) > 5 else "")
                    if remediacion:
                        for t in nombres:
                            session.exec(text(f'ANALYZE "{t}"'))
                        session.commit()
                        estado = "ok"
                        detalle += " · Centinela ejecutó ANALYZE → estadísticas actualizadas"
                        audit("centinela.reparar.analyze", "bd", {"tablas": nombres})
                    sistema.append({"clave": "stats_bd", "label": "Estadísticas de la BD", "estado": estado, "detalle": detalle})
            except Exception as e:  # raiz: vigilancia: un fallo de sonda no tumba el resto del tick; se registra
                session.rollback()
                sistema.append({"clave": "stats_bd", "label": "Estadísticas de la BD", "estado": "warn", "detalle": str(e)[:120]})

        # ── Disco ──
        if vigila("almacenamiento"):
            try:
                du = shutil.disk_usage("/")
                pct = round(du.used / du.total * 100, 1)
                libre = round(du.free / 1e9, 1)
                estado = "error" if pct >= 95 else "warn" if pct >= 85 else "ok"
                detalle = f"{pct}% usado · {libre} GB libres"
                if estado == "error" and remediacion:
                    reparado = disco_seguro.limpiar_temporales_seguros()
                    if reparado["archivos_borrados"]:
                        du2 = shutil.disk_usage("/")
                        pct2 = round(du2.used / du2.total * 100, 1)
                        estado = "error" if pct2 >= 95 else "warn" if pct2 >= 85 else "ok"
                        detalle += (f" · Centinela liberó {reparado['mb_liberados']} MB "
                                    f"({reparado['archivos_borrados']} temporales) → ahora {pct2}%")
                        audit("centinela.reparar.disco", "disco", reparado)
                    else:
                        detalle += " · Centinela no encontró temporales desechables que borrar"
                sistema.append({"clave": "disco", "label": "Disco", "estado": estado, "detalle": detalle})
            except Exception as e:  # raiz: vigilancia: un fallo de sonda no tumba el resto del tick; se registra
                sistema.append({"clave": "disco", "label": "Disco", "estado": "warn", "detalle": str(e)[:120]})

        # ── Memoria (RAM) — nunca reparación autónoma: no hay acción segura para liberar
        # RAM de un proceso multiusuario sin matarlo, y reiniciar el propio backend desde
        # dentro de sí mismo es la operación más peligrosa posible. Solo alerta. ──
        if vigila("memoria"):
            try:
                info = {}
                with open("/proc/meminfo") as f:
                    for line in f:
                        k, v = line.split(":", 1)
                        info[k] = int(v.strip().split()[0])
                total_kb, disp_kb = info["MemTotal"], info.get("MemAvailable", info.get("MemFree", 0))
                pct = round((1 - disp_kb / total_kb) * 100, 1) if total_kb else 0.0
                libre_gb = round(disp_kb / 1e6, 1)
                estado = "error" if pct >= 95 else "warn" if pct >= 85 else "ok"
                sistema.append({"clave": "ram", "label": "Memoria (RAM)", "estado": estado,
                                "detalle": f"{pct}% usada · {libre_gb} GB disponibles"})
            except Exception as e:  # raiz: vigilancia: un fallo de sonda no tumba el resto del tick; se registra
                sistema.append({"clave": "ram", "label": "Memoria (RAM)", "estado": "warn", "detalle": str(e)[:120]})

        # ── Comportamiento de la web (5xx reales) ──
        if vigila("comportamiento"):
            n = errores_recientes(15)
            estado = "error" if n >= 5 else "warn" if n >= 1 else "ok"
            detalle = f"{n} error(es) 5xx en los últimos 15 min" if n else "Sin errores en los últimos 15 min"
            sistema.append({"clave": "comportamiento", "label": "Comportamiento de la web", "estado": estado, "detalle": detalle})

        # ── Backend (proceso responde) ──
        if vigila("backend"):
            sistema.append({"clave": "servidor", "label": "Servidor (API)", "estado": "ok",
                            "detalle": f"En línea · {datetime.now().strftime('%H:%M:%S')}"})

        # ── Integraciones IA (LLM) ──
        if vigila("integraciones_ia"):
            sistema.append(self._check_llm_rescate())

        # ── WhatsApp (Evolution) — detección real + escalada de reparación ──
        if vigila("whatsapp"):
            sistema.append(self._check_whatsapp(centro_id, remediacion, audit))

        # ── Email saliente (SMTP) ──
        if vigila("email_saliente"):
            sistema.append(self._check_integracion_simple(
                centro_id, "email_saliente", "Email saliente (SMTP)",
                lambda cfg_i: smtp_test(cfg_i)))

        # ── Email entrante (IMAP) ──
        if vigila("email_imap"):
            sistema.append(self._check_integracion_simple(
                centro_id, "email_imap", "Email entrante (IMAP)",
                lambda cfg_i: imap_test(cfg_i)))

        # ── Orthanc (DICOM/RX) ──
        if vigila("orthanc"):
            sistema.append(self._check_integracion_simple(
                centro_id, "orthanc", "Orthanc (DICOM/RX)",
                lambda cfg_i: orthanc_ping(cfg_i)))

        # ── Google Drive (multimedia) ──
        if vigila("google_drive"):
            sistema.append(self._check_integracion_simple(
                centro_id, "google_drive", "Google Drive (multimedia)",
                lambda cfg_i: drive_client.test(cfg_i)))

        # ── Web de la clínica — lo que de verdad ve un paciente al abrir el navegador ──
        if vigila("frontend"):
            sistema.append(self._check_frontend())

        # ── App del paciente (Android/iOS) — su API propia, no basta con "el backend vive" ──
        if vigila("app_paciente"):
            sistema.append(self._check_app_paciente())

        # ── IA de radiografías (DentIA / «Analizar IA»): numeración local + nervio/seno en pc-escaner ──
        if vigila("ia_dental"):
            sistema.append(self._check_ia_dental())

        # ── Autenticación — patrones anómalos, detección+alerta pura (nunca bloquea) ──
        if vigila("autenticacion"):
            sistema.append(self._check_autenticacion())

        # ── Trabajos programados — que scheduler.py deje de fallar en silencio ──
        if vigila("trabajos_programados"):
            sistema.append(self._check_trabajos_programados())

        # Integraciones del centro (listado informativo, no gatea nivel)
        rows = session.exec(text(
            "SELECT tipo, nombre, activo FROM integraciones WHERE centro_id=:c ORDER BY tipo"
        ), params={"c": centro_id}).mappings().all()
        integraciones = [{"tipo": r["tipo"], "label": _INTEGR_LABEL.get(r["tipo"], r["nombre"] or r["tipo"]),
                          "estado": "ok" if r["activo"] else "off"} for r in rows]

        nivel = "error" if any(s["estado"] == "error" for s in sistema) else \
                "warn" if any(s["estado"] == "warn" for s in sistema) else "ok"

        self._registrar_bitacora(centro_id, nivel, origen, audit)
        disparada = self._alertar(centro_id, cfg, nivel, sistema, usuario_id, ip)
        return {"nivel": nivel, "activa": True, "sistema": sistema, "integraciones": integraciones,
                "alertaDisparada": disparada, "comprobado": datetime.now().isoformat(timespec="seconds")}

    # ─────────────────────── WhatsApp: detección + escalada ───────────────────────
    def _check_whatsapp(self, centro_id: int, remediacion: bool, audit) -> dict:
        session = self.session
        ig = session.exec(select(Integracion).where(
            Integracion.centro_id == centro_id, Integracion.tipo == "whatsapp",
            Integracion.activo == True)).first()  # noqa: E712
        if not ig or not ig.config:
            return {"clave": "whatsapp", "label": "WhatsApp (Evolution)", "estado": "warn",
                    "detalle": "Sin conector activo"}

        try:
            cli = EvolutionClient(ig.config)
            st = cli.connection_state()
            estado_conn = (st.get("instance") or {}).get("state") or st.get("state")
        except EvolutionError as e:
            estado_conn = None
            _ = e
        ultimo = session.exec(select(Auditoria).where(
            Auditoria.accion == "centinela.reparar.whatsapp", Auditoria.centro_id == centro_id
        ).order_by(Auditoria.created_at.desc())).first()
        paso = (ultimo.detalle or {}).get("paso") if ultimo else None
        hace = (datetime.utcnow() - ultimo.created_at).total_seconds() if ultimo else None

        # Solo cuentan los fallos POSTERIORES a la última reparación, y tras reparar basta uno.
        fallos = whatsapp_monitor.fallos_recientes(session, centro_id, 15,
                                                   desde=ultimo.created_at if ultimo else None)
        umbral = UMBRAL_FALLOS_TRAS_REPARAR if paso in ("instance_restart", "docker_restart") \
            else UMBRAL_FALLOS_WHATSAPP
        mal = estado_conn != "open" or fallos >= umbral

        base_detalle = f"estado={estado_conn or 'desconocido'} · {fallos} fallo(s) de envío en 15 min"

        if not mal:
            if paso and paso != "recuperado":
                audit("centinela.reparar.whatsapp", "whatsapp", {"paso": "recuperado", "paso_previo": paso})
            return {"clave": "whatsapp", "label": "WhatsApp (Evolution)", "estado": "ok", "detalle": base_detalle}

        if not remediacion:
            return {"clave": "whatsapp", "label": "WhatsApp (Evolution)", "estado": "error",
                    "detalle": base_detalle + " · Centinela en solo-lectura, no repara"}

        # Máquina de estados de la escalada — memoria = último Auditoria (sobrevive reinicios).
        if paso is None or paso == "recuperado" or (paso == "agotado" and hace and hace >= ESPERA_REINTENTO_SEG):
            try:
                EvolutionClient(ig.config).restart_instance()
                audit("centinela.reparar.whatsapp", "whatsapp", {"paso": "instance_restart"})
            except EvolutionError as e:
                audit("centinela.reparar.whatsapp", "whatsapp", {"paso": "instance_restart", "error": str(e)[:200]}, exito=False)
            return {"clave": "whatsapp", "label": "WhatsApp (Evolution)", "estado": "warn",
                    "detalle": base_detalle + " · Centinela reinició la instancia, comprobando…"}

        if paso == "instance_restart":
            if hace is not None and hace < ESPERA_SOFT_SEG:
                return {"clave": "whatsapp", "label": "WhatsApp (Evolution)", "estado": "warn",
                        "detalle": base_detalle + " · esperando a que la instancia reconecte…"}
            try:
                restart_contenedor("makingsmiles-evolution", (self._whitelist_contenedores()))
                audit("centinela.reparar.whatsapp", "whatsapp", {"paso": "docker_restart"})
            except DockerError as e:
                audit("centinela.reparar.whatsapp", "whatsapp", {"paso": "docker_restart", "error": str(e)[:200]}, exito=False)
            return {"clave": "whatsapp", "label": "WhatsApp (Evolution)", "estado": "warn",
                    "detalle": base_detalle + " · el reinicio de instancia no bastó, Centinela reinició el contenedor…"}

        if paso == "docker_restart":
            if hace is not None and hace < ESPERA_DOCKER_SEG:
                return {"clave": "whatsapp", "label": "WhatsApp (Evolution)", "estado": "warn",
                        "detalle": base_detalle + " · esperando a que el contenedor levante…"}
            audit("centinela.reparar.whatsapp", "whatsapp", {"paso": "agotado"}, exito=False)
            return {"clave": "whatsapp", "label": "WhatsApp (Evolution)", "estado": "error",
                    "detalle": base_detalle + " · Centinela agotó la reparación autónoma, requiere revisión"}

        # paso == "agotado" y aún no toca reintentar
        return {"clave": "whatsapp", "label": "WhatsApp (Evolution)", "estado": "error",
                "detalle": base_detalle + " · reparación ya agotada, en espera antes de reintentar"}

    def _whitelist_contenedores(self) -> Optional[list[str]]:
        cfg = ConfigService(self.session).resolve("centinela.config", sistema="centinela", default=None) or {}
        lista = (cfg.get("permisos") or {}).get("contenedores_reiniciables")
        return lista if isinstance(lista, list) and lista else None

    # Candidatos conocidos por proveedor para sustituir un modelo descatalogado/roto —
    # verificados con llamada real el 20-sep-2026 (ver infrastructure/llm/openai_compat_client.py).
    # Un 429/402 de CUOTA no se arregla probando otro modelo (es la cuenta, no el modelo):
    # esos casos se dejan para que Ollama/otro proveedor cubra, no se intenta sustituir.
    _CANDIDATOS_MODELO = {
        "groq": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"],
        "openrouter": ["nvidia/nemotron-3-super-120b-a12b:free", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
                       "google/gemma-4-31b-it:free", "z-ai/glm-5.2:free"],
        "gemini": ["gemini-3.6-flash"],
    }
    _URLS = {"groq": "https://api.groq.com/openai/v1", "openrouter": "https://openrouter.ai/api/v1",
             "gemini": "https://generativelanguage.googleapis.com/v1beta/openai"}

    def _es_fallo_de_cuota(self, error: str) -> bool:
        e = error.lower()
        return "429" in e or "402" in e or "quota" in e or "payment" in e or "billing" in e

    def _sustituir_si_hay_alternativa(self, nombre: str, api_key: str, modelo_caido: str, error: str) -> Optional[str]:
        """Prueba, con una llamada REAL, cada candidato de este proveedor hasta encontrar uno
        que responda; si lo encuentra, lo deja sustituido para las próximas llamadas y
        devuelve su nombre. None si no hay ninguno viable (o el fallo es de cuota/pago,
        que cambiar de modelo no soluciona)."""
        if self._es_fallo_de_cuota(error):
            return None
        import asyncio
        from infrastructure.external_apis.openai_compat_client import OpenAICompatClient
        from infrastructure.llm import rescate_override
        for candidato in self._CANDIDATOS_MODELO.get(nombre, []):
            if candidato == modelo_caido:
                continue
            cliente = OpenAICompatClient(base_url=self._URLS[nombre], api_key=api_key, model=candidato)
            try:
                asyncio.run(cliente.chat(messages=[{"role": "user", "content": "OK"}], max_tokens=20))
            except Exception:  # raiz: este candidato tampoco vale, se prueba el siguiente
                continue
            rescate_override.sustituir(nombre, candidato)
            return candidato
        return None

    # ─────────────────────── rescate LLM (Ollama → Groq → OpenRouter → Gemini) ───────────────────────
    def _check_llm_rescate(self) -> dict:
        """Audita los 4 proveedores de la cadena de rescate (ver infrastructure/llm/
        fallback_provider.py) y, si alguno de rescate falló por un modelo roto/descatalogado
        (no por cuota), prueba candidatos reales y lo SUSTITUYE en caliente — no se limita a
        avisar. El propio FallbackProvider ya cae solo al primero que responda en cada
        llamada real; esto además repara el que falló para que vuelva a estar disponible."""
        # La comprobación de cada proveedor de la nube es un chat REAL (gasta cupo). Con la
        # vigilancia cada 60 s eran 1440 llamadas/día por proveedor: agotaba el cupo diario
        # gratuito (Groq 1000/día, OpenRouter) y el rescate estaba muerto justo cuando hacía
        # falta. Se comprueba como mucho una vez por hora; entre medias, el último resultado.
        cache = CentinelaService._llm_rescate_cache
        if cache and (datetime.now() - cache[0]).total_seconds() < self._LLM_RESCATE_CADA_SEG:
            return cache[1]
        resultado = self._check_llm_rescate_real()
        CentinelaService._llm_rescate_cache = (datetime.now(), resultado)
        return resultado

    _LLM_RESCATE_CADA_SEG = 3600
    _llm_rescate_cache: Optional[tuple] = None

    def _check_llm_rescate_real(self) -> dict:
        import asyncio
        from infrastructure.llm.ollama_provider import get_llm_provider
        try:
            provider = get_llm_provider()
            salud = asyncio.run(provider.health_check())
        except Exception as e:  # raiz: un fallo aquí no debe tumbar el resto de Centinela
            return {"clave": "ia", "label": "Integraciones IA", "estado": "error",
                    "detalle": f"No se pudo comprobar la cadena de rescate: {e}"}

        cadena = salud.get("details", {}).get("cadena", [])
        api_keys = {"groq": settings.groq_api_key, "openrouter": settings.openrouter_api_key,
                    "gemini": settings.gemini_api_key_free}
        sustituidos: list[str] = []
        sin_alternativa: list[str] = []
        for c in cadena:
            if c.get("status") == "ok" or c["provider"] == "ollama":
                continue
            nombre = c["provider"]
            error = str(c.get("details", {}).get("error", ""))
            modelo_caido = c.get("model", "")
            nuevo = self._sustituir_si_hay_alternativa(nombre, api_keys.get(nombre, ""), modelo_caido, error)
            if nuevo:
                sustituidos.append(f"{nombre} ({modelo_caido} → {nuevo})")
            else:
                sin_alternativa.append(nombre)

        if sustituidos:
            # Recalcular tras sustituir: la próxima llamada real ya usará el modelo nuevo.
            salud = asyncio.run(get_llm_provider().health_check())
        cadena = salud.get("details", {}).get("cadena", [])
        caidos = [c["provider"] for c in cadena if c.get("status") != "ok"]
        vivos = [c["provider"] for c in cadena if c.get("status") == "ok"]

        if sustituidos:
            estado = "warn" if caidos else "ok"
            detalle = f"Sustituido automáticamente: {', '.join(sustituidos)}."
            if caidos:
                detalle += f" Sin alternativa viable todavía: {', '.join(caidos)} (probablemente cuota/pago, no el modelo)."
            return {"clave": "ia", "label": "Integraciones IA", "estado": estado, "detalle": detalle}

        if not vivos:
            estado, detalle = "error", "NINGÚN proveedor LLM responde (ni el local ni los 3 de rescate) — el chat de los agentes está caído."
        elif caidos:
            estado = "warn"
            detalle = (f"Sirviendo con '{salud.get('provider')}'. Caídos: {', '.join(caidos)} "
                       f"— sin alternativa de modelo (probablemente cuota/pago). Sigue habiendo opción viable.")
        else:
            estado, detalle = "ok", f"Los {len(vivos)} proveedores responden. Sirviendo con '{salud.get('provider')}'."
        return {"clave": "ia", "label": "Integraciones IA", "estado": estado, "detalle": detalle}

    # ─────────────────────── conectores simples (sin reparación) ───────────────────────
    def _check_integracion_simple(self, centro_id: int, tipo: str, label: str, probar) -> dict:
        ig = self.session.exec(select(Integracion).where(
            Integracion.centro_id == centro_id, Integracion.tipo == tipo,
            Integracion.activo == True)).first()  # noqa: E712
        clave = tipo
        if not ig or not ig.config:
            return {"clave": clave, "label": label, "estado": "warn", "detalle": "Sin integración activa"}
        try:
            res = probar(ig.config)
        except Exception as e:  # raiz: cualquier cliente externo puede fallar de formas no previstas
            res = {"ok": False, "error": str(e)}
        if res.get("ok"):
            return {"clave": clave, "label": label, "estado": "ok", "detalle": "Conexión verificada"}
        return {"clave": clave, "label": label, "estado": "error", "detalle": str(res.get("error", "Fallo de conexión"))[:150]}

    # ─────────────────────── web de la clínica ───────────────────────
    def _check_frontend(self) -> dict:
        """Comprueba la web COMO LA VE UN PACIENTE: una petición HTTP real al frontend.

        No repara desde aquí a propósito. La web es un proceso del HOST bajo systemd
        (`makingsmiles-web.service`, Restart=always) y este código corre dentro de un
        contenedor, sin acceso al systemd del anfitrión — pretender repararla desde
        aquí sería una promesa falsa. El reparador real es systemd, que además
        sobrevive a un reinicio de la máquina y a que este backend esté caído;
        Centinela es la segunda capa independiente: detecta, avisa y deja bitácora.

        Y aunque la web esté caída, el paciente NO ve un error de servidor: Caddy
        sirve una página de respaldo propia (ver /home/jmd/caddy/Caddyfile), que es lo
        que garantiza que siempre haya algo que ofrecer.
        """
        import httpx
        from infrastructure.host_net import host_gateway

        url = settings.frontend_health_url or f"http://{host_gateway()}:{settings.frontend_puerto}/"
        try:
            r = httpx.get(url, timeout=6.0, follow_redirects=False)
        except Exception as e:  # raiz: cualquier fallo de red = no se alcanza por la vía directa
            # La web escucha en 127.0.0.1 (por diseño, solo la alcanza Caddy): desde este contenedor la vía
            # directa NO llega aunque la web esté perfecta (falsa alarma permanente desde el 27-oct-2026,
            # 1.902 alertas). Se comprueba entonces como la ve el paciente: por la dirección pública.
            return self._check_frontend_publico(type(e).__name__)
        # Cualquier respuesta HTTP (200, 307 al login, incluso 404) significa que hay web
        # en pie sirviendo. Solo un 5xx indica que está viva pero rota por dentro.
        if r.status_code >= 500:
            return {"clave": "frontend", "label": "Web de la clínica", "estado": "error",
                    "detalle": f"Responde pero falla (HTTP {r.status_code})"}
        return {"clave": "frontend", "label": "Web de la clínica", "estado": "ok",
                "detalle": f"Sirviendo · HTTP {r.status_code}"}

    def _check_frontend_publico(self, motivo_directa: str) -> dict:
        """Sonda por la dirección pública (a través de Caddy). Caddy, si la web cae, sirve su página de
        respaldo con un 200: por eso no basta el código HTTP; la web real lleva `x-powered-by: Next.js`."""
        import httpx

        base = (settings.public_frontend_url or "").rstrip("/")
        try:
            r = httpx.get(f"{base}/login", timeout=8.0, follow_redirects=False)
        except Exception as e:  # raiz: vigilancia: un fallo de sonda no tumba el resto del tick; se registra
            return {"clave": "frontend", "label": "Web de la clínica", "estado": "error",
                    "detalle": f"No responde ({type(e).__name__}) · Caddy está sirviendo la página de respaldo"}
        if r.status_code >= 500:
            return {"clave": "frontend", "label": "Web de la clínica", "estado": "error",
                    "detalle": f"Responde pero falla (HTTP {r.status_code})"}
        if "next.js" not in r.headers.get("x-powered-by", "").lower():
            return {"clave": "frontend", "label": "Web de la clínica", "estado": "error",
                    "detalle": f"La dirección pública no devuelve la web (HTTP {r.status_code}, sin firma de Next.js) · "
                               "Caddy está sirviendo la página de respaldo"}
        return {"clave": "frontend", "label": "Web de la clínica", "estado": "ok",
                "detalle": f"Sirviendo por la dirección pública · HTTP {r.status_code}"}

    # ─────────────────────── app del paciente ───────────────────────
    def _check_app_paciente(self) -> dict:
        """Comprueba que la API de la app del paciente sigue EN PIE y protegida.

        Que el backend responda no implica que la app funcione: si su router deja de
        registrarse (un import roto al desplegar), sus rutas devuelven 404 y la app queda
        inservible mientras el resto de la web va perfecta. Por eso se pregunta por una ruta
        concreta de la app en vez de fiarse del /health general.

        La sonda va SIN credenciales a propósito y espera un 401: eso demuestra a la vez que
        la ruta existe y que la autenticación protege los datos del paciente. No se llama a
        `solicitar-codigo` porque enviaría un OTP real a una persona real.

        El otro modo de fallo —que el paciente no reciba el código— no se comprueba aquí: el
        OTP sale por WhatsApp con respaldo por email, y ambos ya tienen su propio objetivo.
        """
        import httpx

        try:
            r = httpx.get(f"http://localhost:8000{RUTA_SONDA_APP}", timeout=6.0)
        except Exception as e:  # raiz: vigilancia: un fallo de sonda no tumba el resto del tick; se registra
            return {"clave": "app_paciente", "label": "App del paciente", "estado": "error",
                    "detalle": f"Su API no responde ({type(e).__name__})"}
        if r.status_code == 401:
            return {"clave": "app_paciente", "label": "App del paciente", "estado": "ok",
                    "detalle": "API en pie y protegida"}
        if r.status_code == 404:
            return {"clave": "app_paciente", "label": "App del paciente", "estado": "error",
                    "detalle": "Sus rutas han desaparecido (router no cargado): la app no funciona"}
        if r.status_code >= 500:
            return {"clave": "app_paciente", "label": "App del paciente", "estado": "error",
                    "detalle": f"Su API falla (HTTP {r.status_code})"}
        # Un 200 sin token sería una fuga de datos de paciente, no una anomalía menor.
        return {"clave": "app_paciente", "label": "App del paciente", "estado": "error",
                "detalle": f"Responde HTTP {r.status_code} SIN autenticación — revisar de inmediato"}

    # ─────────────────────── IA de radiografías ───────────────────────
    def _check_ia_dental(self) -> dict:
        """DentIA depende de DOS servicios: `ia-dental` (numeración FDI, en este servidor) y el servidor OralGPT de
        nervio/seno/incluidos, que corre en otra máquina (pc-escaner, con GPU) y que arrancaba a mano: si esa máquina se
        reiniciaba o apagaba, la IA perdía el nervio y el seno sin que nadie lo notara. Se sondea el /health de cada uno.
        Numeración caída = error (no hay análisis); solo nervio/seno caído = warn (DentIA sigue numerando y se puede
        marcar a mano)."""
        import httpx
        from infrastructure import ia_dental_client

        clave, label = "ia_dental", "IA de radiografías (DentIA)"
        url_num = (ia_dental_client.IA_DENTAL_URL or "").rstrip("/")
        if not url_num:
            return {"clave": clave, "label": label, "estado": "warn", "detalle": "IA no configurada (IA_DENTAL_URL vacío)"}
        try:
            r = httpx.get(f"{url_num}/health", timeout=6.0)
            r.raise_for_status()
        except Exception as e:  # raiz: cualquier fallo = el servicio de numeración no está
            return {"clave": clave, "label": label, "estado": "error",
                    "detalle": f"La numeración (ia-dental) no responde ({type(e).__name__}): DentIA no puede analizar"}
        url_oral = (settings.oralgpt_health_url or "").strip()
        if not url_oral:
            return {"clave": clave, "label": label, "estado": "ok", "detalle": "Numeración OK · nervio/seno sin vigilar (ORALGPT_HEALTH_URL vacío)"}
        try:
            r2 = httpx.get(url_oral, timeout=6.0)
            d = r2.json() if r2.status_code == 200 else {}
        except Exception as e:  # raiz: vigilancia: un fallo de sonda no tumba el resto del tick; se registra
            return {"clave": clave, "label": label, "estado": "warn",
                    "detalle": f"Numeración OK · el servidor de nervio/seno (pc-escaner) no responde ({type(e).__name__}): "
                               "se analiza solo la numeración"}
        if r2.status_code != 200 or not d.get("ok"):
            return {"clave": clave, "label": label, "estado": "warn",
                    "detalle": f"Numeración OK · el servidor de nervio/seno responde mal (HTTP {r2.status_code})"}
        if not d.get("cuda"):
            return {"clave": clave, "label": label, "estado": "warn",
                    "detalle": "Numeración OK · el servidor de nervio/seno corre SIN GPU (tardará minutos por radiografía)"}
        faltan = sorted({"canal_seno", "11clases"} - set(d.get("modelos") or []))
        if faltan:
            return {"clave": clave, "label": label, "estado": "warn",
                    "detalle": f"Numeración OK · al servidor de nervio/seno le faltan modelos: {', '.join(faltan)}"}
        return {"clave": clave, "label": label, "estado": "ok", "detalle": "Numeración OK · nervio/seno OK (GPU, 2 modelos cargados)"}

    # ─────────────────────── autenticación — detección pura ───────────────────────
    def _check_autenticacion(self) -> dict:
        desde = datetime.utcnow() - timedelta(minutes=15)
        filas = self.session.exec(select(Auditoria.ip, Auditoria.recurso).where(
            Auditoria.accion == "auth.login", Auditoria.exito == False,  # noqa: E712
            Auditoria.created_at >= desde, Auditoria.ip.is_not(None))).all()
        por_ip: dict[str, set] = {}
        for ip_, email_ in filas:
            por_ip.setdefault(ip_, set()).add(email_)
        peor_ip, peor_n = None, 0
        for ip_, emails in por_ip.items():
            if len(emails) > peor_n:
                peor_ip, peor_n = ip_, len(emails)
        estado = "error" if peor_n >= settings.login_alerta_ip_emails_distintos_error else \
                 "warn" if peor_n >= settings.login_alerta_ip_emails_distintos_warn else "ok"
        detalle = (f"{peor_n} cuenta(s) distinta(s) fallando desde la misma IP en 15 min"
                   if peor_n else "Sin patrones anómalos de login")
        return {"clave": "autenticacion", "label": "Autenticación", "estado": estado, "detalle": detalle}

    # ─────────────────────── trabajos programados ───────────────────────
    def _check_trabajos_programados(self) -> dict:
        jobs = jobs_heartbeat.estado_jobs()
        malos = [j for j in jobs if j["estado"] != "ok"]
        estado = "error" if any(j["estado"] == "error" for j in malos) else \
                 "warn" if malos else "ok"
        detalle = ("Todos al día" if not malos else
                   "; ".join(f"{j['job']}: {j['detalle']}" for j in malos))
        return {"clave": "trabajos_programados", "label": "Trabajos programados", "estado": estado, "detalle": detalle}

    # ─────────────────────── bitácora (§6) ───────────────────────
    def _registrar_bitacora(self, centro_id: int, nivel: str, origen: str, audit) -> None:
        _ticks_desde_ultimo[centro_id] = _ticks_desde_ultimo.get(centro_id, 0) + 1
        ultimo = self.session.exec(select(Auditoria).where(
            Auditoria.accion == "centinela.tick", Auditoria.centro_id == centro_id
        ).order_by(Auditoria.created_at.desc())).first()
        anterior = (ultimo.detalle or {}).get("nivel") if ultimo else None
        forzar = origen == "heartbeat_diario"
        if not forzar and anterior == nivel:
            return
        audit("centinela.tick", None, {"nivel": nivel, "anterior": anterior, "origen": origen,
                                        "forzado": forzar, "ticks_desde_ultimo": _ticks_desde_ultimo[centro_id]})
        _ticks_desde_ultimo[centro_id] = 0

    # ─────────────────────── alertas (repara-primero, avisa-si-no-puede) ───────────────────────
    def _alertar(self, centro_id: int, cfg: dict, nivel: str, sistema: list[dict],
                usuario_id: Optional[int], ip: Optional[str]) -> bool:
        if nivel == "ok":
            return False
        alertas_cfg = cfg.get("alertas") or {}
        severidad_min = alertas_cfg.get("severidad_min", "warning")
        if _RANGO_NIVEL[nivel] < _RANGO_SEVERIDAD.get(severidad_min, 1):
            return False

        limites = cfg.get("limites") or {}
        max_hora = int(limites.get("max_alertas_hora") or 20)
        hace_una_hora = datetime.utcnow() - timedelta(hours=1)
        en_ultima_hora = self.session.exec(select(Auditoria).where(
            Auditoria.accion == "centinela.alerta", Auditoria.centro_id == centro_id,
            Auditoria.created_at > hace_una_hora)).all()
        if len(en_ultima_hora) >= max_hora:
            return False

        canales = alertas_cfg.get("canales") or {}
        destinatarios = alertas_cfg.get("destinatarios") or []
        resumen = "; ".join(f"{s['label']}: {s['detalle']}" for s in sistema if s["estado"] != "ok") or "Revisión necesaria"
        enviados: list[str] = []
        if canales.get("email"):
            for d in destinatarios:
                if "@" not in d:
                    continue
                try:
                    if send_email(self.session, d, f"[Centinela] Alerta {nivel} en MakingSmiles", resumen):
                        enviados.append(f"email:{d}")
                except Exception:  # raiz: un destinatario roto no silencia al resto
                    pass
        if canales.get("whatsapp"):
            for d in destinatarios:
                if "@" in d:
                    continue
                try:
                    ComunicacionService(self.session).enviar_texto(centro_id, d, f"⚠️ Centinela ({nivel}): {resumen}")
                    enviados.append(f"whatsapp:{d}")
                except Exception:  # raiz: un destinatario roto no silencia al resto
                    pass

        if (cfg.get("permisos") or {}).get("auditoria", True):
            try:
                AuthService(self.session).audit("centinela.alerta", usuario_id=usuario_id, centro_id=centro_id,
                                                recurso=f"nivel:{nivel}", ip=ip,
                                                detalle={"nivel": nivel, "checks": sistema, "canales_enviados": enviados})
            except Exception:  # raiz: vigilancia: un fallo de sonda no tumba el resto del tick; se registra
                self.session.rollback()
        return True


def purgar_auditoria(session: Session) -> dict:
    """Mantenimiento nocturno (§7): purga por retención — antes vivía DENTRO de `_alertar`
    (se ejecutaba en cada tick, incluso sin incidencia, y solo cubría `centinela.alerta`).
    Ahora es un job único que cubre TODA la actividad de Centinela, respetando la retención
    configurada por centro para `centinela.*`, y una retención de plataforma para el resto."""
    from domain.models.config import Configuracion
    borrados_centinela = 0
    centros_con_cfg = session.exec(select(Configuracion.centro_id).where(
        Configuracion.clave == "centinela.config")).all()
    for cid in centros_con_cfg:
        cfg = ConfigService(session).resolve("centinela.config", centro_id=cid,
                                             sistema="centinela", default=None) or {}
        retencion_dias = int((cfg.get("limites") or {}).get("retencion_dias") or 30)
        corte = datetime.utcnow() - timedelta(days=retencion_dias)
        res = session.exec(text(
            "DELETE FROM auditoria WHERE centro_id=:c AND accion LIKE 'centinela.%' AND created_at < :corte"
        ), params={"c": cid, "corte": corte})
        borrados_centinela += res.rowcount or 0
    corte_plataforma = datetime.utcnow() - timedelta(days=180)
    res2 = session.exec(text(
        "DELETE FROM auditoria WHERE accion NOT LIKE 'centinela.%' AND created_at < :corte"
    ), params={"corte": corte_plataforma})
    session.commit()
    return {"centinela_borrados": borrados_centinela, "resto_borrados": res2.rowcount or 0}
