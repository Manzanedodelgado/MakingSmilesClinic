"""PIN de escritura de Aura — el segundo factor de SuperUser (decisión de jmd, 14-oct-2026).

Aura puede modificar y crear casi todo (usuarios, configuración, agentes, revisión de
Centinela), pero NINGUNA escritura sale sin PIN: SuperUser lo fija en Config → Agentes IA
→ Aura, se guarda como hash (nunca en claro) y cada sesión de Aura queda desbloqueada
15 minutos tras verificarlo. Tres fallos seguidos bloquean la verificación 15 minutos —
mismo criterio anti-fuerza-bruta que el login, porque un PIN que se prueba a ciegas por
chat es tan golpeable como una contraseña.

El desbloqueo vive en MEMORIA del proceso: el PIN gobierna la sesión, no la base de datos.
Al reiniciar el backend (o al caducar el TTL) Aura vuelve a pedirlo. Cada cambio de PIN,
cada desbloqueo y cada fallo queda en auditoría — el valor jamás.
"""
from __future__ import annotations

import time

from sqlmodel import Session

from application.services.auth_service import AuthService
from application.services.config_service import ConfigService
from infrastructure.security import hash_password, verify_password

CLAVE_PIN = "aura.pin_hash"
SISTEMA = "aura"
TTL_SEG = 15 * 60            # sesión desbloqueada: 15 minutos
INTENTOS_MAX = 3             # fallos seguidos antes de bloquear…
BLOQUEO_SEG = 15 * 60        # …y bloqueado otros 15

# (centro_id, usuario_id) -> expira_en (epoch).  /  -> [fallos, bloqueado_hasta]
_desbloqueos: dict[tuple[int, int], float] = {}
_intentos: dict[tuple[int, int], list] = {}


def _audit(session: Session, usuario_id: int | None, centro_id: int,
           accion: str, *, exito: bool = True, detalle: dict | None = None) -> None:
    # Sin envoltorio (regla del gate): un fallo de auditoría PROPAGA — una operación de
    # PIN sin registro no se produce.
    AuthService(session).audit(accion, usuario_id=usuario_id, centro_id=centro_id,
                               exito=exito, detalle=detalle)


def _hash_pin_guardado(session: Session, centro_id: int) -> str | None:
    return ConfigService(session).resolve(CLAVE_PIN, centro_id=centro_id,
                                          sistema=SISTEMA, default=None) or None


def hay_pin(session: Session, centro_id: int) -> bool:
    return _hash_pin_guardado(session, centro_id) is not None


def fijar_pin(session: Session, centro_id: int, usuario_id: int | None, pin: str) -> dict:
    """Fija o cambia el PIN de Aura. El valor se guarda hasheado y NUNCA se audita."""
    pin = (pin or "").strip()
    if not (4 <= len(pin) <= 8 and pin.isdigit()):
        return {"ok": False, "motivo": "El PIN debe tener entre 4 y 8 dígitos."}
    ConfigService(session).set(CLAVE_PIN, hash_password(pin),
                               centro_id=centro_id, sistema=SISTEMA)
    # Un PIN nuevo invalida todo desbloqueo vigente: quien lo cambia, manda.
    for k in [k for k in _desbloqueos if k[0] == centro_id]:
        _desbloqueos.pop(k, None)
    _audit(session, usuario_id, centro_id, "aura.pin.cambiado")
    return {"ok": True}


def estado_pin(session: Session, centro_id: int) -> dict:
    return {"fijado": hay_pin(session, centro_id), "ttl_minutos": TTL_SEG // 60,
            "intentos_max": INTENTOS_MAX}


def desbloquear(session: Session, centro_id: int, usuario_id: int | None, pin: str) -> dict:
    """Verifica el PIN y desbloquea ESTA sesión durante TTL_SEG. Anti-fuerza-bruta:
    INTENTOS_MAX fallos seguidos → BLOQUEO_SEG sin poder intentarlo."""
    key = (centro_id, usuario_id or 0)
    ahora = time.time()
    fallos, hasta = _intentos.get(key, [0, 0.0])
    if hasta > ahora:
        quedan = int((hasta - ahora) // 60) + 1
        _audit(session, usuario_id, centro_id, "aura.pin.bloqueado", exito=False)
        return {"ok": False, "motivo": f"Demasiados fallos: espera {quedan} min."}

    guardado = _hash_pin_guardado(session, centro_id)
    if not guardado:
        return {"ok": False,
                "motivo": "Aura no tiene PIN fijado: fíjalo en Config → Agentes IA → Aura."}
    if not verify_password((pin or "").strip(), guardado):
        fallos += 1
        hasta = ahora + BLOQUEO_SEG if fallos >= INTENTOS_MAX else 0.0
        _intentos[key] = [fallos, hasta]
        _audit(session, usuario_id, centro_id, "aura.pin.fallo", exito=False,
               detalle={"fallos": fallos})
        if hasta:
            return {"ok": False, "motivo": "PIN incorrecto: bloqueado 15 minutos."}
        return {"ok": False, "motivo": f"PIN incorrecto ({INTENTOS_MAX - fallos} intentos más)."}

    _intentos.pop(key, None)
    _desbloqueos[key] = ahora + TTL_SEG
    _audit(session, usuario_id, centro_id, "aura.pin.desbloqueo",
           detalle={"ttl_minutos": TTL_SEG // 60})
    return {"ok": True, "escritura_habilitada_minutos": TTL_SEG // 60}


def desbloqueada(centro_id: int, usuario_id: int | None) -> bool:
    """¿Puede escribir AURA en ESTA sesión ahora mismo? (TTL puro, sin consumir.)"""
    key = (centro_id, usuario_id or 0)
    expira = _desbloqueos.get(key)
    if expira is None:
        return False
    if expira <= time.time():
        _desbloqueos.pop(key, None)
        return False
    return True


def cerrar(centro_id: int, usuario_id: int | None) -> bool:
    """SuperUser puede cerrar el desbloqueo antes de tiempo ("ya no escribas más")."""
    return _desbloqueos.pop((centro_id, usuario_id or 0), None) is not None
