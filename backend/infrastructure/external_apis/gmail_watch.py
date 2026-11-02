"""
Gmail Watch Management — Push notifications via Gmail API watch().

Gmail watch() expira a los 7 días. Este módulo maneja:
- Activación/renovación automática (cron cada 6 días)
- Almacenamiento de estado en BD (configuraciones.clave="gmail.watch")
- Detención manual
- Consulta de estado
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlmodel import Session, select

from domain.models.config import Configuracion, Integracion

logger = logging.getLogger(__name__)

# Etiqueta para el watch de Gmail
# 22-oct-2026: era "Facturas/INBOX", que no existe en el buzon (ninguna carpeta cuelga de
# "Facturas/"). La bandeja de trabajo real es la misma que usa el barrido.
WATCH_LABEL = "Gastos/1. Gastos sin procesar"  # Solo notificaciones de emails en esta etiqueta
WATCH_TOPIC = "projects/makingsmiles-studio/topics/gmail-push"  # Pub/Sub topic (configurar en GCP)


def _get_gmail_credentials(session: Session, centro_id: int) -> Optional[dict]:
    """Obtiene credenciales OAuth de Gmail desde integraciones."""
    ig = session.exec(select(Integracion).where(
        Integracion.centro_id == centro_id,
        Integracion.tipo == "email_imap",
        Integracion.activo == True
    )).first()
    if ig and ig.config:
        return ig.config
    return None


def _get_watch_config(session: Session, centro_id: int) -> dict:
    """Obtiene configuración del watch guardada en BD."""
    cfg = session.exec(select(Configuracion).where(
        Configuracion.centro_id == centro_id,
        Configuracion.clave == "gmail.watch",
        Configuracion.sistema.is_(None),
        Configuracion.usuario_id.is_(None)
    )).first()
    return cfg.valor if cfg and cfg.valor else {}


def _save_watch_config(session: Session, centro_id: int, config: dict) -> None:
    """Guarda configuración del watch en BD (tabla `configuraciones`, clave gmail.watch)."""

    cfg = session.exec(select(Configuracion).where(
        Configuracion.centro_id == centro_id,
        Configuracion.clave == "gmail.watch",
        Configuracion.sistema.is_(None),
        Configuracion.usuario_id.is_(None)
    )).first()

    if cfg:
        cfg.valor = config
        session.add(cfg)
    else:
        session.add(Configuracion(centro_id=centro_id, clave="gmail.watch", valor=config))
    session.commit()



def _get_access_token(credentials: dict) -> Optional[str]:
    """Obtiene access token OAuth2 para Gmail API."""
    # Si ya tenemos token válido, usarlo
    if credentials.get("access_token") and credentials.get("expires_at"):
        expires = datetime.fromisoformat(credentials["expires_at"])
        if expires > datetime.now() + timedelta(minutes=5):
            return credentials["access_token"]
    
    # Refrescar token
    if not credentials.get("refresh_token"):
        return None
    
    try:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": credentials["client_id"],
                "client_secret": credentials["client_secret"],
                "refresh_token": credentials["refresh_token"],
                "grant_type": "refresh_token"
            },
            timeout=10
        )
        if response.status_code != 200:
            logger.error(f"Error refrescando token: {response.text}")
            return None
        
        data = response.json()
        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        
        # Actualizar credenciales
        credentials["access_token"] = access_token
        credentials["expires_at"] = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
        
        return access_token
    except Exception as e:  # raiz: refresh del token Gmail falla (red/HTTP/credenciales) -> None; el caller renovara o pedira reconexion
        logger.error(f"Error refrescando token Gmail: {e}")
        return None


def activar_watch(session: Session, centro_id: int) -> dict:
    """
    Activa o renueva Gmail watch para notificaciones push.
    
    El watch expira a los 7 días. Se debe renovar cada 6 días via cron.
    """
    creds = _get_gmail_credentials(session, centro_id)
    if not creds:
        return {"ok": False, "error": "Credenciales Gmail no configuradas"}
    
    access_token = _get_access_token(creds)
    if not access_token:
        return {"ok": False, "error": "No se pudo obtener access token OAuth"}
    
    # Configurar watch request
    watch_request = {
        "labelIds": ["INBOX"],  # Solo notificaciones de INBOX
        "topicName": WATCH_TOPIC,
        "labelFilterBehavior": "INCLUDE"
    }
    
    try:
        response = httpx.post(
            "https://www.googleapis.com/gmail/v1/users/me/watch",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json=watch_request,
            timeout=15
        )
        
        if response.status_code != 200:
            logger.error(f"Gmail watch activación falló: {response.text}")
            return {"ok": False, "error": f"Gmail API: {response.text[:200]}"}
        
        data = response.json()
        expiration = data.get("expiration")
        history_id = data.get("historyId")
        
        # Calcular fecha expiración (timestamp en ms)
        exp_dt = None
        if expiration:
            exp_dt = datetime.fromtimestamp(int(expiration) / 1000)
        
        # Guardar estado en BD
        config = {
            "activo": True,
            "history_id": history_id,
            "expiration": exp_dt.isoformat() if exp_dt else None,
            "expiration_ts": expiration,
            "ultima_activacion": datetime.now().isoformat(),
            "topic": WATCH_TOPIC
        }
        _save_watch_config(session, centro_id, config)
        
        logger.info(f"Gmail watch activado para centro {centro_id}, expira: {exp_dt}")
        return {
            "ok": True,
            "expiration": exp_dt.isoformat() if exp_dt else None,
            "history_id": history_id,
            "message": "Watch activado correctamente"
        }
        
    except httpx.TimeoutException:
        return {"ok": False, "error": "Timeout activando watch"}
    except Exception as e:  # raiz: alta del watch falla (HTTP/credenciales/BD) -> {ok:False}; se informa sin romper la API
        logger.exception(f"Error activando Gmail watch: {e}")
        return {"ok": False, "error": str(e)}


def detener_watch(session: Session, centro_id: int) -> dict:
    """Detiene Gmail watch (revoca notificaciones push)."""
    creds = _get_gmail_credentials(session, centro_id)
    if not creds:
        return {"ok": False, "error": "Credenciales Gmail no configuradas"}
    
    access_token = _get_access_token(creds)
    if not access_token:
        return {"ok": False, "error": "No se pudo obtener access token OAuth"}
    
    try:
        response = httpx.post(
            "https://www.googleapis.com/gmail/v1/users/me/stop",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            logger.warning(f"Gmail stop watch falló: {response.text}")
        
        # Marcar como inactivo en BD
        config = _get_watch_config(session, centro_id)
        config["activo"] = False
        config["detenido_en"] = datetime.now().isoformat()
        _save_watch_config(session, centro_id, config)
        
        return {"ok": True, "message": "Watch detenido"}
        
    except Exception as e:  # raiz: baja del watch falla (HTTP/BD) -> {ok:False}; se informa sin romper la API
        logger.exception(f"Error deteniendo Gmail watch: {e}")
        return {"ok": False, "error": str(e)}


def estado_watch(session: Session, centro_id: int) -> dict:
    """Obtiene estado actual del Gmail watch."""
    config = _get_watch_config(session, centro_id)
    
    if not config:
        return {
            "activo": False,
            "configurado": False,
            "message": "Watch no configurado"
        }
    
    activo = config.get("activo", False)
    expiration_str = config.get("expiration")
    
    expirado = False
    if expiration_str:
        try:
            exp_dt = datetime.fromisoformat(expiration_str)
            expirado = exp_dt < datetime.now()
            if expirado:
                activo = False
        except Exception:  # raiz: expiration del watch ilegible -> se conserva el estado previo en vez de inventarlo
            logger.warning("gmail-watch: expiration ilegible, se conserva estado previo", exc_info=True)
    
    return {
        "activo": activo,
        "configurado": True,
        "expiration": expiration_str,
        "expirado": expirado,
        "history_id": config.get("history_id"),
        "ultima_activacion": config.get("ultima_activacion"),
        "topic": config.get("topic"),
        "message": "Watch activo" if activo else ("Watch expirado" if expirado else "Watch inactivo")
    }


def renovar_watch_si_cerca(session: Session, centro_id: int, dias_antes: int = 1) -> dict:
    """
    Renueva watch si expira en menos de `dias_antes` días.
    Debe llamarse via cron cada día.
    """
    estado = estado_watch(session, centro_id)
    
    if not estado["configurado"] or not estado["activo"]:
        # No hay watch o está inactivo → activar
        logger.info(f"Watch inactivo para centro {centro_id}, activando...")
        return activar_watch(session, centro_id)
    
    if estado["expirado"]:
        logger.warning(f"Watch expirado para centro {centro_id}, renovando...")
        return activar_watch(session, centro_id)
    
    # Verificar si expira pronto
    if estado["expiration"]:
        try:
            exp_dt = datetime.fromisoformat(estado["expiration"])
            dias_restantes = (exp_dt - datetime.now()).days
            if dias_restantes <= dias_antes:
                logger.info(f"Watch expira en {dias_restantes} días para centro {centro_id}, renovando...")
                return activar_watch(session, centro_id)
        except Exception:  # raiz: no se puede evaluar la caducidad del watch -> se asume vigente y no se renueva a ciegas
            logger.warning("gmail-watch: no se pudo evaluar caducidad, se asume vigente", exc_info=True)
    
    return {"ok": True, "message": "Watch vigente, no requiere renovación", "dias_restantes": dias_restantes if 'dias_restantes' in locals() else None}


def procesar_notificacion_push(session: Session, centro_id: int, message_id: str, history_id: str) -> dict:
    """
    Procesa notificación push de Gmail.
    
    Gmail envía notificación a Pub/Sub → Cloud Function/Cloud Run → este endpoint.
    Aquí obtenemos el message_id y lo procesamos.
    """
    # Actualizar history_id en config
    config = _get_watch_config(session, centro_id)
    config["history_id"] = history_id
    config["ultima_notificacion"] = datetime.now().isoformat()
    _save_watch_config(session, centro_id, config)
    
    # El procesamiento real del email se hace en background task
    # para no bloquear la respuesta a Pub/Sub (timeout 10s)
    return {"ok": True, "message_id": message_id, "history_id": history_id}


__all__ = [
    "activar_watch",
    "detener_watch",
    "estado_watch",
    "renovar_watch_si_cerca",
    "procesar_notificacion_push",
]
