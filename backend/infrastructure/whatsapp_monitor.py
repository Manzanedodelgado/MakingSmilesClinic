"""Detección de fallos REALES de envío por WhatsApp (infraestructura), sin mandar mensajes
de prueba sintéticos (gastarían cupo y podrían parecer spam a WhatsApp).

Se instrumenta el único punto por el que YA pasa todo envío real de la app
(`ComunicacionService.enviar_texto`/`enviar_documento`) — cada fallo real de Evolution deja
constancia aquí. A diferencia del contador de errores 5xx (`error_monitor.py`, en memoria,
volumen potencialmente alto), este SÍ se persiste en `Auditoria`: es comparativamente escaso
(solo envíos reales) y necesita sobrevivir reinicios del proceso porque alimenta la máquina
de estados de reparación de Centinela (instance_restart → docker_restart → alerta).
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from application.services.auth_service import AuthService
from domain.models.auditoria import Auditoria

ACCION_FALLO = "centinela.whatsapp.fallo_envio"


def registrar_fallo(session: Session, centro_id: int, operacion: str, motivo: str) -> None:
    AuthService(session).audit(ACCION_FALLO, centro_id=centro_id, recurso=operacion,
                               detalle={"motivo": motivo[:300]}, exito=False)


def fallos_recientes(session: Session, centro_id: int, minutos: int = 15,
                     desde: Optional[datetime] = None) -> int:
    """`desde` (opcional) acota aún más la ventana: Centinela lo usa para no contar los
    fallos ANTERIORES a su última reparación (si no, un WhatsApp ya recuperado seguiría
    pareciendo roto y escalaría a reiniciar el contenedor sin necesidad)."""
    limite = datetime.utcnow() - timedelta(minutes=minutos)
    desde = max(desde, limite) if desde else limite
    return len(session.exec(select(Auditoria).where(
        Auditoria.accion == ACCION_FALLO, Auditoria.centro_id == centro_id,
        Auditoria.created_at >= desde)).all())
