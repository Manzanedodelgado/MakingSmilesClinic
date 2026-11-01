"""Helper único de auditoría — fuente compartida."""
from application.services.auth_service import AuthService


def _audit(session, user, centro_id, accion, recurso, request, detalle=None):
    AuthService(session).audit(accion, usuario_id=user.usuario_id, centro_id=centro_id, recurso=recurso,
                               detalle=detalle, ip=request.client.host if request.client else None)
