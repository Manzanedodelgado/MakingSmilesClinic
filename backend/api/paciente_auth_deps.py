"""🧿 MEMBRANA PACIENTE — dependencia de autenticación de la app nativa del paciente.

Puerta separada de auth_deps.py (CENTINELA de personal): JWT distinto (tipo="paciente"),
sin cookie ni X-Centro-Id — el centro va dentro del propio token (un paciente pertenece
a un único centro). Las apps nativas (iOS/Android) guardan el token en almacenamiento
seguro del sistema (Keychain / EncryptedSharedPreferences) y lo mandan como
`Authorization: Bearer`, nunca por cookie.
"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from infrastructure.security import decode_access_token

bearer_paciente = HTTPBearer(auto_error=False)


class CurrentPaciente:
    def __init__(self, paciente_id: int, centro_id: int):
        self.paciente_id = paciente_id
        self.centro_id = centro_id


def get_current_paciente(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_paciente),
) -> CurrentPaciente:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")
    payload = decode_access_token(creds.credentials)
    if not payload or payload.get("tipo") != "paciente":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado")
    return CurrentPaciente(
        paciente_id=int(payload["paciente_id"]),
        centro_id=int(payload["centro_id"]),
    )
