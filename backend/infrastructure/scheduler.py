"""Scheduler de automatización (infraestructura).

Un job cada minuto que, para cada centro con WhatsApp activo y `automatizacion_activa`,
corre el motor de automatización en horario laboral (L-S, 8-21h). Apagado de facto:
si ningún centro tiene la integración activa, no hace nada.
"""
from datetime import datetime
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from application.services.automatizacion_service import AutomatizacionService
from application.services.automatizacion_triggers import ahora_clinica
from application.services.config_service import ConfigService
from domain.config.settings import settings
from domain.models.config import Integracion
from infrastructure.config.db import engine
from infrastructure import jobs_heartbeat

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_lock_conn = None   # conexión dedicada que mantiene el lock consultivo mientras viva el proceso

# Producción corre con `--workers 4` (deploy/backend.Dockerfile): SIN este lock, los 4
# procesos arrancarían cada uno su propio BackgroundScheduler y ejecutarían los mismos
# jobs 4 veces en paralelo — WhatsApp automático duplicado a pacientes, reparaciones de
# Centinela cuadruplicadas (4x restart de Evolution), alertas repetidas. El lock
# consultivo de Postgres (visible a nivel de servidor, no por conexión) asegura que
# SOLO el primer proceso que lo consiga programe algo; los demás no hacen nada.
_ADVISORY_LOCK_KEY = 918_273_645


def _adquirir_lock_scheduler() -> bool:
    global _lock_conn
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (_ADVISORY_LOCK_KEY,))
        obtenido = bool(cur.fetchone()[0])
        cur.close()
        if not obtenido:
            conn.close()
            return False
        _lock_conn = conn   # se mantiene abierta a propósito: el lock vive con la conexión
        return True
    except Exception:  # raiz: si Postgres no está listo aún, no arranca el scheduler
        logger.warning("scheduler: Postgres no listo, no se arranca en este worker")
        return False


def _en_horario(ahora: datetime) -> bool:
    return ahora.weekday() != 6 and 8 <= ahora.hour < 21   # L-S, 8:00-20:59


def _tick() -> None:
    # El contenedor corre en UTC; "horario laboral" es hora de Madrid (mismo helper que usan
    # las ventanas de recordatorio_1h/2h etc. en automatizacion_triggers.py) — con datetime.now()
    # a secas, este gate se desplazaba 1-2h y podía saltarse o abrir de más el tick de cada minuto.
    ahora = ahora_clinica()
    if not _en_horario(ahora):
        jobs_heartbeat.marcar_exito("automatizacion")   # fuera de horario a propósito, no es un fallo
        return
    with Session(engine) as session:
        # Centros con WhatsApp conectado y automatización activada en Config › IA's › Alex.
        integraciones = session.exec(select(Integracion).where(
            Integracion.tipo == "whatsapp", Integracion.activo == True)).all()  # noqa: E712
        for ig in integraciones:
            alex = ConfigService(session).for_scope(
                centro_id=ig.centro_id, sistema="ia").get("agente.alex") or {}
            if not alex.get("automatizacion"):
                continue
            try:
                AutomatizacionService(session).ejecutar(ig.centro_id, enviar=True)
            except Exception:  # raiz: un centro no debe tumbar el tick
                logger.exception("scheduler: automatización falló en centro %s", ig.centro_id)
    jobs_heartbeat.marcar_exito("automatizacion")


def _procesar_buzones() -> None:
    """Ingesta automática de facturas: para cada centro con IMAP activo, procesa los correos
    NUEVOS del INBOX (mismo flujo que el botón 'Procesar buzón', idempotente) y, por separado,
    los de Facturas/Facturas revisadas (correos que el usuario confirmó a mano tras revisar
    Incidencias — esos se registran siempre, nunca se descartan). Se lanza 2 veces al día; un
    centro que falle no tumba a los demás."""
    from application.services.intake_service import IntakeService, CARPETA_ENTRADA, ETIQUETA_REVISADAS
    with Session(engine) as session:
        imaps = session.exec(select(Integracion).where(
            Integracion.tipo == "email_imap", Integracion.activo == True)).all()  # noqa: E712
        for ig in imaps:
            carpeta = (ig.config or {}).get("carpeta") or CARPETA_ENTRADA
            try:
                svc = IntakeService(session, ig.centro_id)
                svc.procesar_buzon(carpeta, execute=True, throttle=3.0)
                # Tras procesar, saca del buzón lo ya tratado (no-op si INTAKE_MOVER_GMAIL≠1).
                svc.archivar_bandeja(carpeta)
            except Exception:  # raiz: un centro no debe tumbar el job
                logger.exception("scheduler: ingesta buzón falló en centro %s", ig.centro_id)
            try:
                IntakeService(session, ig.centro_id).procesar_revisadas(
                    ETIQUETA_REVISADAS, execute=True, throttle=3.0)
            except Exception:  # raiz: un centro no debe tumbar el job
                logger.exception("scheduler: revisadas falló en centro %s", ig.centro_id)
    jobs_heartbeat.marcar_exito("ingesta_facturas")


def _cuadrar_bancos() -> None:
    """Motor de conciliación: casa facturas, genera los recurrentes (alquiler, parking, autofacturas
    de colaboradores, impuestos/SS) y deja el resto en revisión. 1 vez al día; idempotente."""
    from application.services.conciliacion_service import ConciliacionService
    with Session(engine) as session:
        centros = session.exec(select(Integracion.centro_id).where(
            Integracion.tipo == "email_imap", Integracion.activo == True).distinct()).all()  # noqa: E712
        for cid in centros:
            # Respeta Config→IA's→Gestor→«Acceso a datos»: si el ámbito es "solo facturas", la
            # conciliación (que toca pagos/banco) NO corre para ese centro.
            gcfg = ConfigService(session).resolve("gestor.config", centro_id=cid, sistema="gestor", default=None) or {}
            if (gcfg.get("permisos") or {}).get("acceso_datos", "facturas_pagos") == "facturas":
                continue
            try:
                ConciliacionService(session, cid).cuadrar(execute=True)
            except Exception:  # raiz: un centro no tumba el job
                logger.exception("scheduler: conciliación falló en centro %s", cid)
    jobs_heartbeat.marcar_exito("conciliacion_banco")


def _envio_gestoria() -> None:
    """Envío automático a la asesoría: cada día comprueba los centros con `gestoria.envio_auto` activo
    y, si hoy es el día programado (y no se mandó ya este mes), les manda los datos. Idempotente."""
    from datetime import date
    from application.services.gestoria_service import GestoriaService
    from domain.models.config import Configuracion
    with Session(engine) as session:
        centros = session.exec(select(Configuracion.centro_id).where(
            Configuracion.clave == "gestoria.envio_auto").distinct()).all()
        hoy = date.today()
        for cid in centros:
            if cid is None:
                continue
            try:
                GestoriaService(session).enviar_programado(cid, hoy)
            except Exception:  # raiz: un centro no tumba el job
                logger.exception("scheduler: envío gestoría falló en centro %s", cid)
    jobs_heartbeat.marcar_exito("envio_gestoria")


def _caducar_contratos() -> None:
    """Colaboradores cuyo 'contrato hasta' ya venció → se marcan inactivos (Colaborador.activo=False).
    NO borra nada: el histórico (citas/tratamientos anteriores) permanece intacto; solo deja de
    admitir agenda/selectores nuevos. Idempotente. La reactivación es manual (renovar la fecha +
    casilla Activo). 1 vez al día."""
    from datetime import date
    from domain.models.core import Colaborador
    with Session(engine) as session:
        vencidos = session.exec(select(Colaborador).where(
            Colaborador.activo == True,  # noqa: E712
            Colaborador.contrato_fin.isnot(None),
            Colaborador.contrato_fin < date.today())).all()
        for col in vencidos:
            col.activo = False
            session.add(col)
        if vencidos:
            session.commit()
    jobs_heartbeat.marcar_exito("caducar_contratos")


def _caducar_presupuestos() -> None:
    """Escribe la caducidad de presupuestos (regla 3 meses) que antes se hacía como
    efecto secundario de un GET (api/pacientes_router.py). El GET ahora es puro — solo
    este job persiste el cambio de estado. 1 vez al día."""
    from domain.models.economico import Presupuesto
    from api.pacientes_router import _presupuestos_caducados
    with Session(engine) as session:
        pres = session.exec(select(Presupuesto).where(Presupuesto.estado_id.in_((0, 1)))).all()
        caducados = _presupuestos_caducados(pres)
        for pr in caducados:
            pr.estado_id = 2
            session.add(pr)
        if caducados:   # sus líneas Presupuestado → Caducado (6 de estados_tratamiento)
            from sqlalchemy import text
            session.connection().execute(text(
                "UPDATE presupuesto_lineas SET estado = 6, updated_at = now() "
                "WHERE presupuesto_id = ANY(:ids) AND estado = 1"), {"ids": [pr.id for pr in caducados]})
        session.commit()
        # Aceptados fuera de plazo (6 / 9 implantes / 24 ortodoncia) → Cancelado.
        from application.services.presupuesto_service import cancelar_fuera_de_plazo
        cancelar_fuera_de_plazo(session)
    jobs_heartbeat.marcar_exito("caducar_presupuestos")


# ─────────────────────── CENTINELA — tick programado (detectar + reparar + bitácora) ───────────────────────
# Intervalo base = el mínimo permitido por el slider de la UI (10-600s). Por dentro, cada
# centro decide si le toca según SU `intervalo_seg` propio — evita registrar/desregistrar
# jobs dinámicamente por centro (frágil con BackgroundScheduler). Perder este reloj en un
# reload es inofensivo (como mucho se hace una comprobación de más), a diferencia del
# estado de reparación de WhatsApp, que sí vive en Auditoria (sobrevive reinicios).
_ultima_ejecucion_centinela: dict[int, datetime] = {}


def _tick_centinela() -> None:
    from domain.models.core import Centro
    from application.services.centinela_service import CentinelaService
    ahora = datetime.utcnow()
    with Session(engine) as session:
        centros = session.exec(select(Centro.id)).all()
        for cid in centros:
            cfg = ConfigService(session).resolve("centinela.config", centro_id=cid,
                                                  sistema="centinela", default=None) or {}
            if cfg and not cfg.get("activa", True):
                continue
            intervalo = max(10, min(600, int((cfg.get("vigilancia") or {}).get("intervalo_seg", 60) or 60)))
            last = _ultima_ejecucion_centinela.get(cid)
            if last and (ahora - last).total_seconds() < intervalo:
                continue
            _ultima_ejecucion_centinela[cid] = ahora
            try:
                CentinelaService(session).ejecutar(cid, origen="scheduler")
            except Exception:  # raiz: un centro no debe tumbar el tick ni a los demás
                logger.exception("scheduler: centinela falló en centro %s", cid)
    jobs_heartbeat.marcar_exito("centinela")


# ─────────────────────── MANTENIMIENTO PROACTIVO — nocturno, no reactivo ───────────────────────
def _mantenimiento_habilitado() -> bool:
    """`permisos.mantenimiento_proactivo` (default true) — apagarlo SOLO desactiva este
    bloque de mantenimiento, no la vigilancia reactiva. Operaciones de host/BD completas
    (no por centro): se ejecutan salvo que TODOS los centros con config guardada lo hayan
    desactivado explícitamente."""
    from domain.models.core import Centro
    with Session(engine) as session:
        centros = session.exec(select(Centro.id)).all()
        if not centros:
            return True
        for cid in centros:
            cfg = ConfigService(session).resolve("centinela.config", centro_id=cid,
                                                 sistema="centinela", default=None) or {}
            if (cfg.get("permisos") or {}).get("mantenimiento_proactivo", True):
                return True
        return False


def _mantenimiento_analyze_nocturno() -> None:
    """ANALYZE proactivo de todas las tablas relevantes (no destructivo, no bloquea) —
    corre siempre que `permisos.mantenimiento_proactivo` esté activo, independientemente
    de `modo_accion` (que solo gobierna la reparación REACTIVA ante un fallo detectado)."""
    if not _mantenimiento_habilitado():
        jobs_heartbeat.marcar_exito("mantenimiento_analyze")
        return
    from sqlalchemy import text as _text
    with Session(engine) as session:
        try:
            tablas = session.exec(_text(
                "SELECT relname FROM pg_stat_user_tables WHERE pg_total_relation_size(relid) > 1048576"
            )).all()
            for (t,) in tablas:
                session.exec(_text(f'ANALYZE "{t}"'))
        except Exception:  # raiz: scheduler: un centro/job que falla no tumba el tick global; se registra
            logger.exception("scheduler: analyze nocturno falló")
            session.rollback()
    jobs_heartbeat.marcar_exito("mantenimiento_analyze")


def _purgar_password_resets() -> None:
    from sqlalchemy import text as _text
    with Session(engine) as session:
        try:
            session.exec(_text("DELETE FROM password_resets WHERE expira_at < :ahora"),
                        params={"ahora": datetime.utcnow()})
            session.commit()
        except Exception:  # raiz: scheduler: un centro/job que falla no tumba el tick global; se registra
            logger.exception("scheduler: purga password_resets falló")
            session.rollback()
    jobs_heartbeat.marcar_exito("purgar_password_resets")


def _purgar_auditoria_job() -> None:
    from application.services.centinela_service import purgar_auditoria
    with Session(engine) as session:
        try:
            purgar_auditoria(session)
        except Exception:  # raiz: scheduler: un centro/job que falla no tumba el tick global; se registra
            logger.exception("scheduler: purga auditoría falló")
            session.rollback()
    jobs_heartbeat.marcar_exito("purgar_auditoria")


def _detector_rx() -> None:
    """Detecta RX nuevas en Orthanc y las exporta a Drive (archivo del paciente). Best-effort."""
    from application.services.radiologia_export_service import detectar_y_exportar
    with Session(engine) as session:
        try:
            detectar_y_exportar(session)
        except Exception:  # raiz: scheduler: un centro/job que falla no tumba el tick global; se registra
            logger.exception("scheduler: detector RX falló")
            session.rollback()
    jobs_heartbeat.marcar_exito("detector_rx")


def _mantenimiento_disco() -> None:
    if not _mantenimiento_habilitado():
        jobs_heartbeat.marcar_exito("mantenimiento_disco")
        return
    from infrastructure import disco_seguro
    disco_seguro.limpiar_temporales_seguros()
    jobs_heartbeat.marcar_exito("mantenimiento_disco")


def _copia_seguridad() -> None:
    """Copia de seguridad programada (Centinela): 15:00 y 22:00, L-V.

    Si falla, NO se queda en el log: se dispara el mismo aviso que cualquier otra
    incidencia de Centinela, porque una copia que falla en silencio es exactamente igual
    de inútil que no tener copias — y no se descubre hasta que hace falta restaurar.
    """
    from application.services.backup_service import BackupService
    from application.services.centinela_service import CentinelaService
    from application.services.config_service import ConfigService as _Cfg
    from domain.models.core import Centro
    with Session(engine) as session:
        centro_id = session.exec(select(Centro.id)).first()
        try:
            res = BackupService(session).ejecutar(centro_id=centro_id)
        except Exception as e:  # raiz: un fallo aquí no puede tumbar el scheduler
            res = {"exito": False, "errores": [str(e)[:300]]}
        if not res.get("exito") and centro_id:
            cfg = _Cfg(session).resolve("centinela.config", centro_id=centro_id,
                                         sistema="centinela", default=None) or {}
            try:
                CentinelaService(session)._alertar(
                    centro_id, cfg, "error",
                    [{"clave": "backup", "label": "Copia de seguridad", "estado": "error",
                      "detalle": "; ".join(res.get("errores") or ["fallo desconocido"])[:300]}],
                    None, None)
            except Exception:  # raiz: scheduler: un centro/job que falla no tumba el tick global; se registra
                logger.exception("scheduler: alerta de backup falló")
                session.rollback()
    jobs_heartbeat.marcar_exito("copia_seguridad")


def _heartbeat_centinela() -> None:
    """Fuerza una fila diaria de bitácora por centro activo, aunque nada haya cambiado —
    cumple 'registrar siempre' sin generar miles de filas/día (ver centinela_service.py §6)."""
    from domain.models.core import Centro
    from application.services.centinela_service import CentinelaService
    with Session(engine) as session:
        for cid in session.exec(select(Centro.id)).all():
            cfg = ConfigService(session).resolve("centinela.config", centro_id=cid,
                                                  sistema="centinela", default=None) or {}
            if cfg and not cfg.get("activa", True):
                continue
            try:
                CentinelaService(session).ejecutar(cid, origen="heartbeat_diario")
            except Exception:  # raiz: scheduler: un centro/job que falla no tumba el tick global; se registra
                logger.exception("scheduler: heartbeat centinela falló en centro %s", cid)
    jobs_heartbeat.marcar_exito("heartbeat_centinela")


def iniciar_scheduler() -> None:
    global _scheduler
    if _scheduler or not settings.scheduler_enabled:
        return
    if not _adquirir_lock_scheduler():
        return   # otro worker de este mismo backend ya tiene el lock — este no programa nada
    _scheduler = BackgroundScheduler(timezone="Europe/Madrid")
    _scheduler.add_job(_tick, "interval", minutes=1, id="automatizacion", max_instances=1,
                       coalesce=True)
    # Ingesta de facturas del buzón: 2 veces al día (08:00 y 20:00, hora de Madrid).
    _scheduler.add_job(_procesar_buzones, "cron", hour="8,20", minute=0, id="ingesta_facturas",
                       max_instances=1, coalesce=True)
    # Motor de conciliación banco↔factura: 1 vez al día (08:30), tras la ingesta.
    _scheduler.add_job(_cuadrar_bancos, "cron", hour=8, minute=30, id="conciliacion_banco",
                       max_instances=1, coalesce=True)
    # Envío automático a la asesoría: se comprueba a diario (07:00); manda solo el día programado.
    _scheduler.add_job(_envio_gestoria, "cron", hour=7, minute=0, id="envio_gestoria",
                       max_instances=1, coalesce=True)
    # Caducidad de presupuestos (regla 3 meses): antes vivía en el GET, ahora aquí. 06:00.
    _scheduler.add_job(_caducar_presupuestos, "cron", hour=6, minute=0, id="caducar_presupuestos",
                       max_instances=1, coalesce=True)
    # Contratos vencidos de colaboradores → inactivo (no destructivo). 06:10, tras presupuestos.
    _scheduler.add_job(_caducar_contratos, "cron", hour=6, minute=10, id="caducar_contratos",
                       max_instances=1, coalesce=True)
    # Detector de RX nuevas en Orthanc → export a Drive (archivo del paciente). Cada 30s.
    _scheduler.add_job(_detector_rx, "interval", seconds=30, id="detector_rx",
                       max_instances=1, coalesce=True)
    # Centinela: tick base cada 10s (el mínimo del slider de la UI); cada centro decide por
    # dentro si le toca según su propio intervalo_seg — detecta, repara, y solo avisa si no puede.
    _scheduler.add_job(_tick_centinela, "interval", seconds=10, id="centinela", max_instances=1,
                       coalesce=True)
    # Mantenimiento proactivo — nocturno, escalonado (no reactivo a ningún fallo detectado).
    _scheduler.add_job(_mantenimiento_analyze_nocturno, "cron", hour=3, minute=0,
                       id="mantenimiento_analyze", max_instances=1, coalesce=True)
    _scheduler.add_job(_purgar_password_resets, "cron", hour=4, minute=0,
                       id="purgar_password_resets", max_instances=1, coalesce=True)
    _scheduler.add_job(_purgar_auditoria_job, "cron", hour=4, minute=30,
                       id="purgar_auditoria", max_instances=1, coalesce=True)
    _scheduler.add_job(_mantenimiento_disco, "cron", hour=5, minute=0,
                       id="mantenimiento_disco", max_instances=1, coalesce=True)
    _scheduler.add_job(_heartbeat_centinela, "cron", hour=6, minute=30,
                       id="heartbeat_centinela", max_instances=1, coalesce=True)
    # Copias de seguridad: 15:00 y 22:00, de lunes a viernes (hora de Madrid).
    # `misfire_grace_time` alto: si a esa hora el servidor estaba apagado o saturado, la
    # copia se hace en cuanto pueda en vez de saltársela en silencio hasta el día siguiente.
    _scheduler.add_job(_copia_seguridad, "cron", day_of_week="mon-fri", hour="15,22", minute=0,
                       id="copia_seguridad", max_instances=1, coalesce=True,
                       misfire_grace_time=3600)
    _scheduler.start()


def parar_scheduler() -> None:
    global _scheduler, _lock_conn
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _lock_conn:
        try:
            cur = _lock_conn.cursor()
            cur.execute("SELECT pg_advisory_unlock(%s)", (_ADVISORY_LOCK_KEY,))
            cur.close()
        except Exception:  # raiz: scheduler: un centro/job que falla no tumba el tick global; se registra
            logger.debug("scheduler: unlock advisory falló al parar", exc_info=True)
        _lock_conn.close()
        _lock_conn = None
