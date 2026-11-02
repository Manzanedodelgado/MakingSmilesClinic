"""Heartbeat en memoria de los jobs programados (infraestructura) — para que Centinela
pueda vigilar "¿los jobs de scheduler.py siguen vivos?" sin que cada uno deje de fallar en
silencio (`except Exception: pass`) por completo. Aceptable perderlo en un reload: en el
peor caso se detecta un job mudo un poco más tarde, nunca se oculta un fallo real más allá
de un ciclo de reinicio del proceso.
"""
from datetime import datetime, timedelta

_ultimo_exito: dict[str, datetime] = {}

# job_id → periodo esperado en segundos (el objetivo `trabajos_programados` da margen ×3).
PERIODOS_ESPERADOS_SEG: dict[str, int] = {
    "automatizacion": 60,
    "ingesta_facturas": 12 * 3600,
    "conciliacion_banco": 24 * 3600,
    "envio_gestoria": 24 * 3600,
    "caducar_presupuestos": 24 * 3600,
    "centinela": 60,
    "mantenimiento_analyze": 24 * 3600,
    "purgar_password_resets": 24 * 3600,
    "purgar_auditoria": 24 * 3600,
    "mantenimiento_disco": 24 * 3600,
    "heartbeat_centinela": 24 * 3600,
    # 15:00 y 22:00 L-V: el hueco más largo es de viernes 22:00 a lunes 15:00 (~65 h).
    "copia_seguridad": 65 * 3600,
}


def marcar_exito(job_id: str) -> None:
    _ultimo_exito[job_id] = datetime.utcnow()


def estado_jobs() -> list[dict]:
    ahora = datetime.utcnow()
    out = []
    for job_id, periodo in PERIODOS_ESPERADOS_SEG.items():
        ultimo = _ultimo_exito.get(job_id)
        margen = timedelta(seconds=periodo * 3)
        if ultimo is None:
            estado = "warn"   # aún no ha corrido ninguna vez desde que arrancó el proceso
            detalle = "sin ejecución registrada todavía"
        elif ahora - ultimo > margen:
            estado = "error"
            detalle = f"sin éxito desde {ultimo.isoformat(timespec='minutes')}"
        else:
            estado = "ok"
            detalle = f"último éxito {ultimo.isoformat(timespec='minutes')}"
        out.append({"job": job_id, "estado": estado, "detalle": detalle})
    return out
