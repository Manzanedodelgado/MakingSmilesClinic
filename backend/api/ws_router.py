"""
WebSocket Router — Tiempo real para Gestor IA Multimodal.

Eventos:
- gasto_nuevo: Se registró una factura nueva
- gasto_actualizado: Se actualizó una factura existente
- gasto_duplicado: Se detectó duplicado
- incidencia_nueva: Nueva incidencia para revisión
- procesamiento_error: Error en el pipeline
- watch_status: Cambio en estado Gmail watch
"""

import json
import logging
from datetime import datetime
from typing import Dict, Set

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from infrastructure.config.db import get_session

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger(__name__)

# Gestor de conexiones activas por centro
class ConnectionManager:
    def __init__(self):
        # centro_id -> set of (websocket, user_id)
        self.active_connections: Dict[int, Set[tuple]] = {}
    
    async def connect(self, websocket: WebSocket, centro_id: int, user_id: int):
        await websocket.accept()
        if centro_id not in self.active_connections:
            self.active_connections[centro_id] = set()
        self.active_connections[centro_id].add((websocket, user_id))
        logger.info(f"WS conectado: centro={centro_id}, user={user_id}, total={len(self.active_connections[centro_id])}")
    
    def disconnect(self, websocket: WebSocket, centro_id: int, user_id: int):
        if centro_id in self.active_connections:
            self.active_connections[centro_id].discard((websocket, user_id))
            if not self.active_connections[centro_id]:
                del self.active_connections[centro_id]
        logger.info(f"WS desconectado: centro={centro_id}, user={user_id}")
    
    async def send_to_centro(self, centro_id: int, message: dict):
        """Envía mensaje a todas las conexiones de un centro."""
        if centro_id not in self.active_connections:
            return
        
        message_str = json.dumps(message)
        disconnected = []
        
        for websocket, user_id in self.active_connections[centro_id]:
            try:
                await websocket.send_text(message_str)
            except Exception as e:  # raiz: cliente con conexión ya caída al enviar; se descarta la conexión y se limpia
                logger.warning(f"Error enviando WS a centro {centro_id}: {e}")
                disconnected.append((websocket, user_id))
        
        # Limpiar desconectados
        for ws, uid in disconnected:
            self.disconnect(ws, centro_id, uid)
    
    async def send_to_user(self, centro_id: int, user_id: int, message: dict):
        """Envía mensaje a un usuario específico en un centro."""
        if centro_id not in self.active_connections:
            return
        
        message_str = json.dumps(message)
        for websocket, uid in self.active_connections[centro_id]:
            if uid == user_id:
                try:
                    await websocket.send_text(message_str)
                except Exception:  # raiz: cliente inalcanzable al enviar; se omite sin romper la difusión
                    logger.debug("ws: cliente %s inalcanzable, se omite", uid, exc_info=True)


manager = ConnectionManager()


# Eventos predefinidos
class WSEvents:
    GASTO_NUEVO = "gasto_nuevo"
    GASTO_ACTUALIZADO = "gasto_actualizado"
    GASTO_DUPLICADO = "gasto_duplicado"
    INCIDENCIA_NUEVA = "incidencia_nueva"
    PROCESAMIENTO_ERROR = "procesamiento_error"
    WATCH_STATUS = "watch_status"
    PROCESAMIENTO_INICIADO = "procesamiento_iniciado"
    PROCESAMIENTO_COMPLETADO = "procesamiento_completado"


async def emitir_gasto_nuevo(centro_id: int, gasto_data: dict):
    """Emite evento de gasto nuevo a todas las conexiones del centro."""
    await manager.send_to_centro(centro_id, {
        "event": WSEvents.GASTO_NUEVO,
        "data": gasto_data,
        "timestamp": datetime.utcnow().isoformat()
    })


async def emitir_gasto_actualizado(centro_id: int, gasto_data: dict):
    await manager.send_to_centro(centro_id, {
        "event": WSEvents.GASTO_ACTUALIZADO,
        "data": gasto_data,
        "timestamp": datetime.utcnow().isoformat()
    })


async def emitir_incidencia_nueva(centro_id: int, incidencia_data: dict):
    await manager.send_to_centro(centro_id, {
        "event": WSEvents.INCIDENCIA_NUEVA,
        "data": incidencia_data,
        "timestamp": datetime.utcnow().isoformat()
    })


async def emitir_procesamiento_error(centro_id: int, error_data: dict):
    await manager.send_to_centro(centro_id, {
        "event": WSEvents.PROCESAMIENTO_ERROR,
        "data": error_data,
        "timestamp": datetime.utcnow().isoformat()
    })


async def emitir_watch_status(centro_id: int, status_data: dict):
    await manager.send_to_centro(centro_id, {
        "event": WSEvents.WATCH_STATUS,
        "data": status_data,
        "timestamp": datetime.utcnow().isoformat()
    })


async def emitir_procesamiento_iniciado(centro_id: int, message_id: str):
    await manager.send_to_centro(centro_id, {
        "event": WSEvents.PROCESAMIENTO_INICIADO,
        "data": {"message_id": message_id},
        "timestamp": datetime.utcnow().isoformat()
    })


async def emitir_procesamiento_completado(centro_id: int, resultado: dict):
    await manager.send_to_centro(centro_id, {
        "event": WSEvents.PROCESAMIENTO_COMPLETADO,
        "data": resultado,
        "timestamp": datetime.utcnow().isoformat()
    })


# WebSocket endpoint principal
@router.websocket("/gestoria/{centro_id}")
async def websocket_gestoria(
    websocket: WebSocket,
    centro_id: int,
    token: str = Query(...),  # JWT token como query param
):
    """WebSocket para tiempo real en Gestoría/Facturación."""
    from api.auth_deps import CurrentUser
    from application.services.auth_service import AuthService
    from infrastructure.config.db import get_session
    from infrastructure.security import decode_access_token

    # Validar token y obtener usuario/centro. No se puede reutilizar `get_current_user`
    # (depende de Request y del sistema de Depends de HTTP), así que se validan aquí las
    # MISMAS primitivas: firma del JWT + tipo 'centro' + acceso al centro + permiso.
    session = next(get_session())
    try:
        payload = decode_access_token(token)
        if not payload or payload.get("tipo") != "centro":
            await websocket.close(code=4001, reason="Token inválido")
            return
        user = CurrentUser(usuario_id=int(payload["sub"]), nombre=payload.get("nombre", ""),
                           accesos=payload.get("accesos", []))

        # El centro va en `accesos` (lista), no en un campo `centro_id` del usuario.
        if not any(a.get("centro_id") == centro_id for a in user.accesos):
            await websocket.close(code=4003, reason="Centro no autorizado")
            return

        perms = AuthService(session).permisos_de(user.usuario_id, centro_id)
        if "gestoria.ver" not in perms:
            await websocket.close(code=4003, reason="Sin permisos de gestoría")
            return

        # Conectar

        await manager.connect(websocket, centro_id, user.usuario_id)
        
        # Enviar estado inicial
        await websocket.send_text(json.dumps({
            "event": "connected",
            "data": {"centro_id": centro_id, "user_id": user.usuario_id},
            "timestamp": datetime.utcnow().isoformat()
        }))
        
        # Mantener conexión viva
        try:
            while True:
                data = await websocket.receive_text()
                # Ping/pong o comandos del cliente
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                except json.JSONDecodeError:
                    logger.debug("ws: mensaje no-JSON ignorado", exc_info=True)
        except WebSocketDisconnect:
            return  # cliente ido: terminar el bucle en vez de caer al error genérico
        except Exception as e:  # raiz: error inesperado en el bucle WS (mensaje/canal); se cierra limpio vía finally
            logger.error(f"Error en WS: {e}")
        finally:
            manager.disconnect(websocket, centro_id, user.usuario_id)
    
    finally:
        session.close()


# El endpoint /ws/test (echo sin autenticación) se retiró en la auditoría del 25-ago-2026:
# era una ruta pública registrada en producción. Para probar, usar /ws/gestoria/{centro_id}
# con un token válido.


# Funciones helper para importar en otros módulos
def get_ws_manager() -> ConnectionManager:
    return manager


__all__ = [
    "router",
    "manager",
    "WSEvents",
    "emitir_gasto_nuevo",
    "emitir_gasto_actualizado",
    "emitir_incidencia_nueva",
    "emitir_procesamiento_error",
    "emitir_watch_status",
    "emitir_procesamiento_iniciado",
    "emitir_procesamiento_completado",
    "get_ws_manager",
]