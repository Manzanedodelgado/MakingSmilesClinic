"""COMUNICACIÓN / WhatsApp — endpoints (capa de interfaz). Solo BBDD nueva.

Bandeja de conversaciones, envío de mensajes, configuración Evolution (por centro)
y webhook entrante. Permisos: comunicacion.ver / comunicacion.editar. El webhook
es público pero validado por el `webhook_secret` de la integración del centro.
"""
import asyncio
import json
import logging

import httpx

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from api.audit_helper import _audit
from api.auth_deps import CurrentUser, get_current_centro, require_permission
from application.services.automatizacion_service import AutomatizacionService
from application.services.comunicacion_service import ComunicacionService
from domain.models.config import Integracion
from infrastructure.config.db import get_session
from infrastructure.external_apis.evolution_api import EvolutionError
from infrastructure.realtime import bus

router = APIRouter(prefix="/comunicacion", tags=["comunicación"])

VER = "comunicacion.ver"
EDITAR = "comunicacion.editar"


def _svc(session: Session) -> ComunicacionService:
    return ComunicacionService(session)


# ─────────────────────── ESTADO WHATSAPP ───────────────────────
# Las credenciales se editan en Config › IA's › Alex › Canales (CanalesIA). Aquí
# solo estado/QR operativos y envío. Una sola fuente de verdad.
@router.get("/whatsapp/estado")
def estado(centro_id: int = Depends(get_current_centro),
           user: CurrentUser = Depends(require_permission(VER)),
           session: Session = Depends(get_session)) -> dict:
    return _svc(session).estado(centro_id)


# ─────────────────────── PAUSA GLOBAL DE LA IA (barra de WhatsApp / panel /ia) ───────────────────────
# Los métodos de servicio (estado_ia_global/pausar_ia_global/reanudar_ia_global) ya existían;
# faltaba exponerlos — el frontend (page.tsx de /comunicacion y /ia) ya los llamaba y daba 404.
@router.get("/ia/estado")
def ia_estado(centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission(VER)),
             session: Session = Depends(get_session)) -> dict:
    return _svc(session).estado_ia_global(centro_id)


class PausarIaIn(BaseModel):
    minutos: int = 20


@router.post("/ia/pausar")
def ia_pausar(data: PausarIaIn,
             centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission(EDITAR)),
             session: Session = Depends(get_session)) -> dict:
    return _svc(session).pausar_ia_global(centro_id, data.minutos)


@router.post("/ia/reanudar")
def ia_reanudar(centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission(EDITAR)),
               session: Session = Depends(get_session)) -> dict:
    return _svc(session).reanudar_ia_global(centro_id)


@router.get("/whatsapp/qr")
def qr(centro_id: int = Depends(get_current_centro),
       user: CurrentUser = Depends(require_permission(VER)),
       session: Session = Depends(get_session)) -> dict:
    return _svc(session).qr(centro_id)


@router.post("/whatsapp/desvincular")
def desvincular(centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission(EDITAR)),
                session: Session = Depends(get_session)) -> dict:
    """Cierra la sesión de WhatsApp para re-vincular otro teléfono (luego /whatsapp/qr)."""
    return _svc(session).desvincular(centro_id)


# ─────────────────────── ENVÍO ───────────────────────
class EnviarIn(BaseModel):
    telefono: str
    texto: str


@router.post("/whatsapp/enviar")
def enviar(data: EnviarIn, request: Request,
           centro_id: int = Depends(get_current_centro),
           user: CurrentUser = Depends(require_permission(EDITAR)),
           session: Session = Depends(get_session)) -> dict:
    try:
        res = _svc(session).enviar_texto(centro_id, data.telefono, data.texto)
    except EvolutionError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"WhatsApp send failed: {e}")
    try:
        _audit(session, user, centro_id, "enviar", "comunicacion/whatsapp", request, data.telefono)
    except Exception as audit_err:  # raiz: fallo de auditoria -> se registra con traza y NO bloquea el envio ya entregado
        logger = logging.getLogger("comunicacion.audit")
        logger.error(f"Audit failed in enviar endpoint: {audit_err}", exc_info=True)
    return res


@router.post("/whatsapp/enviar-media")
async def enviar_media(telefono: str, file: UploadFile = File(...), caption: str = Form(""), request: Request = None,
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission(EDITAR)),
                       session: Session = Depends(get_session)) -> dict:
    contenido = await file.read()
    try:
        res = _svc(session).enviar_media(centro_id, telefono, contenido, file.filename, file.content_type, caption or None)
    except EvolutionError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"WhatsApp send failed: {e}")
    if request:
        _audit(session, user, centro_id, "enviar-media", "comunicacion/whatsapp", request, telefono)
    return res


# ─────────────────────── TIEMPO REAL (SSE) ───────────────────────
@router.get("/stream")
async def stream(centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission(VER))) -> StreamingResponse:
    """Empuja al frontend los eventos publicados en `bus` (mensajes entrantes/salientes)
    para este centro. Heartbeat cada 15s para mantener viva la conexión a través de proxies."""
    async def gen():
        q = await bus.subscribe(centro_id)
        try:
            while True:
                try:
                    evento = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(evento)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            bus.unsubscribe(centro_id, q)
    return StreamingResponse(gen(), media_type="text/event-stream")


# ─────────────────────── CONVERSACIONES ───────────────────────
@router.get("/conversaciones")
def conversaciones(archivadas: bool = False,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(VER)),
                   session: Session = Depends(get_session)) -> dict:
    return {"data": _svc(session).listar_conversaciones(centro_id, archivadas)}


@router.get("/conversaciones/{conv_id}/mensajes")
def mensajes(conv_id: int,
             centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission(VER)),
             session: Session = Depends(get_session)) -> dict:
    return {"data": _svc(session).listar_mensajes(centro_id, conv_id)}


class ResponderIn(BaseModel):
    texto: str


@router.post("/conversaciones/{conv_id}/mensajes")
def responder(conv_id: int, data: ResponderIn, request: Request,
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission(EDITAR)),
              session: Session = Depends(get_session)) -> dict:
    try:
        res = _svc(session).responder_conversacion(centro_id, conv_id, data.texto)
    except EvolutionError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"WhatsApp send failed: {e}")
    except Exception as e:  # raiz: error al procesar la respuesta -> traza + 500 controlado; nunca silencio
        logger = logging.getLogger("comunicacion.error")
        logger.error(f"Error en responder conversacion {conv_id}: {e}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al procesar el mensaje")
    try:
        _audit(session, user, centro_id, "responder", f"comunicacion/conv/{conv_id}", request)
    except Exception as audit_err:  # raiz: fallo de auditoria -> se registra con traza y NO bloquea el mensaje ya enviado
        logger = logging.getLogger("comunicacion.audit")
        logger.error(f"Audit failed in responder endpoint: {audit_err}", exc_info=True)
    return res


class EditarMensajeIn(BaseModel):
    texto: str


@router.patch("/conversaciones/{conv_id}/mensajes/{msg_id}")
def editar_mensaje(conv_id: int, msg_id: int, data: EditarMensajeIn, request: Request,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(EDITAR)),
                   session: Session = Depends(get_session)) -> dict:
    """Edita el texto de un mensaje NUESTRO ya enviado — solo si el paciente aún no lo ha
    leído (Evolution deja editar de verdad para ambos en esa ventana, no después)."""
    try:
        _svc(session).editar_mensaje(centro_id, conv_id, msg_id, data.texto)
    except PermissionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except EvolutionError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"WhatsApp rechazó la edición: {e}") from e
    _audit(session, user, centro_id, "mensaje.editar", f"mensaje:{msg_id}", request)
    return {"ok": True}


@router.delete("/conversaciones/{conv_id}/mensajes/{msg_id}")
def borrar_mensaje(conv_id: int, msg_id: int, request: Request,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(EDITAR)),
                   session: Session = Depends(get_session)) -> dict:
    """Borra un mensaje NUESTRO para AMBOS (delete-for-everyone real vía Evolution) — solo si
    el paciente aún no lo ha leído."""
    try:
        _svc(session).borrar_mensaje(centro_id, conv_id, msg_id)
    except PermissionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except EvolutionError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"WhatsApp rechazó el borrado: {e}") from e
    _audit(session, user, centro_id, "mensaje.borrar", f"mensaje:{msg_id}", request)
    return {"ok": True}


@router.post("/conversaciones/{conv_id}/media")
async def enviar_media_conv(conv_id: int, file: UploadFile = File(...), caption: str = Form(""), request: Request = None,
                            centro_id: int = Depends(get_current_centro),
                            user: CurrentUser = Depends(require_permission(EDITAR)),
                            session: Session = Depends(get_session)) -> dict:
    contenido = await file.read()
    res = _svc(session).enviar_media_conv(centro_id, conv_id, contenido, file.filename, file.content_type, caption or None)
    if request:
        _audit(session, user, centro_id, "enviar-media", f"comunicacion/conv/{conv_id}", request)
    return res


@router.post("/conversaciones/{conv_id}/leida")
def leida(conv_id: int,
          centro_id: int = Depends(get_current_centro),
          user: CurrentUser = Depends(require_permission(VER)),
          session: Session = Depends(get_session)) -> dict:
    if not _svc(session).marcar_leida(centro_id, conv_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    return {"ok": True}


class EstadoIn(BaseModel):
    estado: str


@router.patch("/conversaciones/{conv_id}/estado")
def cambiar_estado(conv_id: int, data: EstadoIn,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(EDITAR)),
                   session: Session = Depends(get_session)) -> dict:
    if not _svc(session).set_estado(centro_id, conv_id, data.estado):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    return {"ok": True}


@router.post("/conversaciones/{conv_id}/archivar")
def archivar(conv_id: int,
             centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission(EDITAR)),
             session: Session = Depends(get_session)) -> dict:
    if not _svc(session).archivar(centro_id, conv_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    return {"ok": True}


@router.post("/conversaciones/{conv_id}/desarchivar")
def desarchivar(conv_id: int,
               centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission(EDITAR)),
               session: Session = Depends(get_session)) -> dict:
    if not _svc(session).desarchivar(centro_id, conv_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    return {"ok": True}


@router.post("/conversaciones/{conv_id}/flujo/cortar")
def cortar_flujo(conv_id: int, request: Request,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission(EDITAR)),
                 session: Session = Depends(get_session)) -> dict:
    """Saca la conversación del flujo de WhatsApp en curso (el próximo mensaje empieza de cero)."""
    if not _svc(session).cortar_flujo(centro_id, conv_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    _audit(session, user, centro_id, "flujo.cortar", f"comunicacion/conv/{conv_id}", request)
    return {"ok": True}


class PausarConvIn(BaseModel):
    minutos: int = 60


@router.post("/conversaciones/{conv_id}/ia/pausar")
def pausar_ia_conversacion(conv_id: int, data: PausarConvIn, request: Request,
                           centro_id: int = Depends(get_current_centro),
                           user: CurrentUser = Depends(require_permission(EDITAR)),
                           session: Session = Depends(get_session)) -> dict:
    """La IA deja de contestar en ESTA conversación durante `minutos`."""
    if not _svc(session).pausar_ia_conversacion(centro_id, conv_id, data.minutos):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    _audit(session, user, centro_id, "ia.pausar", f"comunicacion/conv/{conv_id}", request,
           {"minutos": data.minutos})
    return {"ok": True}


@router.post("/conversaciones/{conv_id}/ia/reanudar")
def reanudar_ia_conversacion(conv_id: int, request: Request,
                             centro_id: int = Depends(get_current_centro),
                             user: CurrentUser = Depends(require_permission(EDITAR)),
                             session: Session = Depends(get_session)) -> dict:
    if not _svc(session).reanudar_ia_conversacion(centro_id, conv_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    _audit(session, user, centro_id, "ia.reanudar", f"comunicacion/conv/{conv_id}", request)
    return {"ok": True}


class NotaIn(BaseModel):
    texto: str


@router.post("/conversaciones/{conv_id}/notas")
def agregar_nota(conv_id: int, data: NotaIn,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission(EDITAR)),
                 session: Session = Depends(get_session)) -> dict:
    m = _svc(session).agregar_nota(centro_id, conv_id, data.texto)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada o nota vacía")
    return m


@router.post("/conversaciones/{conv_id}/no-leida")
def no_leida(conv_id: int,
             centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission(EDITAR)),
             session: Session = Depends(get_session)) -> dict:
    if not _svc(session).marcar_no_leida(centro_id, conv_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    return {"ok": True}


@router.post("/conversaciones/{conv_id}/fijar-conv")
def fijar_conv(conv_id: int,
               centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission(EDITAR)),
               session: Session = Depends(get_session)) -> dict:
    if not _svc(session).fijar_conversacion(centro_id, conv_id, True):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    return {"ok": True}


@router.post("/conversaciones/{conv_id}/desfijar-conv")
def desfijar_conv(conv_id: int,
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(EDITAR)),
                  session: Session = Depends(get_session)) -> dict:
    if not _svc(session).fijar_conversacion(centro_id, conv_id, False):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    return {"ok": True}


@router.post("/conversaciones/{conv_id}/urgente")
def marcar_urgente(conv_id: int,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(EDITAR)),
                   session: Session = Depends(get_session)) -> dict:
    if not _svc(session).marcar_urgente(centro_id, conv_id, True):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    return {"ok": True}


@router.post("/conversaciones/{conv_id}/no-urgente")
def desmarcar_urgente(conv_id: int,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission(EDITAR)),
                      session: Session = Depends(get_session)) -> dict:
    if not _svc(session).marcar_urgente(centro_id, conv_id, False):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    return {"ok": True}


# ─────────────────────── CONTEXTO PACIENTE ───────────────────────
@router.get("/contexto/{telefono}")
def contexto(telefono: str,
             centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission(VER)),
             session: Session = Depends(get_session)) -> dict:
    return _svc(session).contexto_paciente(centro_id, telefono)


# ─────────────────────── PLANTILLAS ───────────────────────
class PlantillaIn(BaseModel):
    id: int | None = None
    nombre: str
    cuerpo: str
    disparador: str | None = None
    tipo: str | None = "texto"
    activo: bool | None = True


@router.get("/plantillas")
def listar_plantillas(centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission(VER)),
                      session: Session = Depends(get_session)) -> dict:
    return {"data": _svc(session).listar_plantillas(centro_id)}


@router.put("/plantillas")
def guardar_plantilla(data: PlantillaIn, request: Request,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission(EDITAR)),
                      session: Session = Depends(get_session)) -> dict:
    res = _svc(session).guardar_plantilla(centro_id, data.model_dump(), user.usuario_id)
    _audit(session, user, centro_id, "guardar", "comunicacion/plantillas", request)
    return res


@router.delete("/plantillas/{pid}")
def borrar_plantilla(pid: int, centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission(EDITAR)),
                     session: Session = Depends(get_session)) -> dict:
    _svc(session).borrar_plantilla(centro_id, pid)
    return {"ok": True}


# ─────────────────────── AGENTE (probador Config › IA's › Alex) ───────────────────────
class ProbarAgenteIn(BaseModel):
    texto: str


@router.post("/agente/probar")
def probar_agente(data: ProbarAgenteIn,
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(EDITAR)),
                  session: Session = Depends(get_session)) -> dict:
    """Corre el agente Alex REAL en modo simular: no envía por WhatsApp ni muta datos
    (crear/mover cita, presupuesto, escalar quedan simulados). No toca el toggle del
    canal (Config › IA's › Alex › Canales): el agente sigue OFF para pacientes reales,
    esto es solo un sandbox de prueba para quien administra."""
    from application.services.agente_service import AgenteService
    from infrastructure.external_apis.llm_client import LLMError
    try:
        res = AgenteService(session).responder(
            centro_id, telefono=f"probador-{user.usuario_id}", texto=data.texto,
            enviar=False, simular=True)
        return {"ok": True, "respuesta": res.get("respuesta")}
    except LLMError as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────── CHAT IA (/ia/chat) — sandbox de entrenamiento por agente ───────────────────────
AGENTES_CHAT = {"alex": "Alex", "gestoria_gastos": "Gestor IA · Gastos"}


class ChatAgenteIn(BaseModel):
    agente: str
    texto: str
    historial: list[dict] | None = None
    escenario: dict | None = None   # {rol: paciente|staff, protocolo: <id>} para el entrenamiento


@router.post("/agente/chat")
def chat_agente(data: ChatAgenteIn,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission(EDITAR)),
                session: Session = Depends(get_session)) -> dict:
    if data.agente not in AGENTES_CHAT:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Agente desconocido: {data.agente}")
    from application.services.agente_service import AgenteService
    from infrastructure.external_apis.llm_client import LLMError
    try:
        res = AgenteService(session).chat_entrenamiento(
            centro_id, data.agente, data.texto, data.historial, user.usuario_id,
            escenario=data.escenario)
        return {"ok": True, "respuesta": res.get("respuesta")}
    except LLMError as e:
        return {"ok": False, "error": str(e)}


class CorreccionIn(BaseModel):
    agente: str
    entrada: str
    propuesta: str
    correccion: str


@router.post("/agente/chat/corregir")
def corregir_chat(data: CorreccionIn,
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(EDITAR)),
                  session: Session = Depends(get_session)) -> dict:
    """Guarda una corrección del Chat IA como ejemplo de entrenamiento futuro DE ESE agente."""
    from application.services.agente_service import AgenteService
    return AgenteService(session).guardar_correccion(
        centro_id, data.agente, data.entrada, data.propuesta, data.correccion, user.usuario_id)


@router.get("/agente/revisiones")
def revisiones_pendientes(centro_id: int = Depends(get_current_centro),
                          user: CurrentUser = Depends(require_permission(VER)),
                          session: Session = Depends(get_session)) -> dict:
    """Bandeja de revisión humana de Alex: respuestas a pacientes retenidas porque
    `agente.alex.revision_humana` está activo (Config › Agentes IA)."""
    from application.services.agente_service import AgenteService
    return {"revisiones": AgenteService(session).revisiones_pendientes(centro_id)}


class ResolverRevisionIn(BaseModel):
    accion: str                     # aprobar | editar | descartar
    texto: str | None = None        # obligatorio con editar


@router.post("/agente/revisiones/{revision_id}")
def resolver_revision(revision_id: int, data: ResolverRevisionIn, request: Request,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission(EDITAR)),
                      session: Session = Depends(get_session)) -> dict:
    """aprobar → se envía tal cual; editar → se envía el texto corregido y queda como ejemplo
    de entrenamiento de Alex; descartar → no se envía."""
    from application.services.agente_service import AgenteService
    r = AgenteService(session).resolver_revision(centro_id, revision_id, data.accion, data.texto,
                                                 user.usuario_id)
    if r.get("ok"):
        _audit(session, user, centro_id, "alex.revision", f"revision:{revision_id}", request,
               {"accion": data.accion})
    return r


@router.get("/estadisticas")
def estadisticas(dias: int = 30,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission(VER)),
                 session: Session = Depends(get_session)) -> dict:
    """Agregados REALES para los indicadores de estado de /ia — nada inventado."""
    filas = session.execute(text("""
        SELECT
            (SELECT count(*) FROM agente_revisiones WHERE centro_id=:c AND estado='pendiente') AS revisiones_pendientes,
            (SELECT count(*) FROM agente_revisiones WHERE centro_id=:c AND estado IN ('aprobada','editada')
                AND revisado_at >= now() - (:dias || ' days')::interval) AS revisiones_aprobadas,
            (SELECT count(*) FROM agente_revisiones WHERE centro_id=:c AND estado='editada'
                AND revisado_at >= now() - (:dias || ' days')::interval) AS revisiones_editadas,
            (SELECT count(*) FROM agente_revisiones WHERE centro_id=:c AND estado='descartada'
                AND revisado_at >= now() - (:dias || ' days')::interval) AS revisiones_descartadas,
            (SELECT count(*) FROM conversaciones WHERE centro_id=:c AND archivada=false AND estado='abierta') AS conversaciones_abiertas,
            (SELECT count(*) FROM conversaciones WHERE centro_id=:c AND archivada=false AND estado='pendiente') AS conversaciones_pendientes,
            (SELECT count(*) FROM conversaciones WHERE centro_id=:c AND archivada=false AND estado='resuelta') AS conversaciones_resueltas,
            (SELECT count(*) FROM conversaciones WHERE centro_id=:c AND archivada=false AND coalesce(tags,'') ILIKE '%urgencia%') AS conversaciones_urgentes,
            (SELECT count(*) FROM mensajes m JOIN conversaciones c ON c.id=m.conversacion_id
                WHERE c.centro_id=:c AND m.direccion='saliente' AND m.generado_por_ia=true
                AND m.enviado_at >= now() - (:dias || ' days')::interval) AS mensajes_generados_por_ia,
            (SELECT count(*) FROM mensajes m JOIN conversaciones c ON c.id=m.conversacion_id
                WHERE c.centro_id=:c AND m.direccion='saliente' AND m.generado_por_ia=false
                AND m.enviado_at >= now() - (:dias || ' days')::interval) AS mensajes_del_equipo
    """), {"c": centro_id, "dias": dias}).mappings().first()
    return dict(filas) if filas else {}


# ─────────────────────── MODELOS DE IA (por agente) ───────────────────────
@router.get("/llm/modelos-disponibles")
def modelos_disponibles(agente: str,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission(VER)),
                        session: Session = Depends(get_session)) -> dict:
    """Catálogo REAL de modelos del proveedor configurado para ese agente (o el compartido
    si no tiene fila propia) — nunca una lista fija: siempre lo que el proveedor ofrece hoy."""
    from application.services.llm_config import resolver_llm

    cfg = resolver_llm(session, centro_id, agente)
    if not cfg or not cfg.get("base_url"):
        raise HTTPException(status.HTTP_409_CONFLICT, "LLM no configurado para este agente")
    try:
        r = httpx.get(cfg["base_url"].rstrip("/") + "/models",
                      headers={"Authorization": f"Bearer {cfg.get('api_key', '')}"}, timeout=20)
        r.raise_for_status()
        modelos = sorted(m["id"] for m in r.json().get("data", []))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"No se pudo consultar el proveedor: {e}") from e
    return {"modeloActual": cfg.get("model"), "modelos": modelos}


# ─────────────────────── AUTOMATIZACIÓN ───────────────────────
@router.post("/automatizacion/preview")
def automatizacion_preview(centro_id: int = Depends(get_current_centro),
                           user: CurrentUser = Depends(require_permission(VER)),
                           session: Session = Depends(get_session)) -> dict:
    """Qué se enviaría AHORA (sin enviar ni registrar nada). Para verificar triggers."""
    return AutomatizacionService(session).ejecutar(centro_id, enviar=False)


@router.post("/automatizacion/ejecutar")
def automatizacion_ejecutar(request: Request,
                            centro_id: int = Depends(get_current_centro),
                            user: CurrentUser = Depends(require_permission(EDITAR)),
                            session: Session = Depends(get_session)) -> dict:
    """Ejecuta los disparadores y ENVÍA (requiere WhatsApp activo y maestro encendido)."""
    try:
        res = AutomatizacionService(session).ejecutar(centro_id, enviar=True)
    except PermissionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    _audit(session, user, centro_id, "ejecutar", "comunicacion/automatizacion", request)
    return res


# ─────────────────────── WEBHOOK (público, validado por secreto del centro) ─────
@router.post("/webhook/{centro_id}")
async def webhook(centro_id: int, request: Request,
                  token: str | None = None,
                  session: Session = Depends(get_session)) -> dict:
    ig = session.exec(select(Integracion).where(
        Integracion.centro_id == centro_id, Integracion.tipo == "whatsapp")).first()
    cfg = (ig.config or {}) if ig else {}
    secret = cfg.get("webhook_hmac") or cfg.get("webhook_secret")
    if not secret or token != secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Webhook no autorizado")
    payload = await request.json()

    # FIX B7: validar que conversación pertenece al centro
    from domain.models.comunicacion import Conversacion
    telefono = (payload.get("data", {}).get("key", {}).get("remoteJid") or "").split("@")[0]
    if telefono:
        conv = session.exec(select(Conversacion).where(
            Conversacion.centro_id == centro_id,
            Conversacion.canal == "whatsapp"
        )).first()
        # Nota: se crea automáticamente si no existe, so this is defensive check

    return _svc(session).procesar_webhook(centro_id, payload)
