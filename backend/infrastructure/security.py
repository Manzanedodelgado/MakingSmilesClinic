"""Primitivas de seguridad (infraestructura).

Hash de contraseñas (bcrypt) y emisión/validación de JWT. Aislado aquí para que
ni el dominio ni la API conozcan la librería concreta.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt

from domain.config.settings import settings


# ───────────────────────── Contraseñas ─────────────────────────
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ───────────────────────── JWT ─────────────────────────
def create_access_token(payload: dict[str, Any], expires_minutes: Optional[int] = None) -> str:
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    to_encode = {**payload, "exp": expire}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    """Devuelve el payload si el token es válido y no ha expirado; None si no."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
