"""Contador en memoria de errores 5xx recientes — señal de "comportamiento de la web"
para Centinela (Config→IA's→Centinela→Vigilancia). Vive en memoria de proceso, no en BD:
esto responde a "¿está fallando la web AHORA?", no un histórico a largo plazo — un
reinicio/reload del backend limpia la cuenta a propósito, no es un bug."""
from collections import deque
from datetime import datetime, timedelta
from threading import Lock

_eventos: deque[datetime] = deque()
_lock = Lock()
_VENTANA_MAX = timedelta(hours=1)  # no crece sin límite aunque nadie consulte nunca


def registrar_error() -> None:
    ahora = datetime.utcnow()
    with _lock:
        _eventos.append(ahora)
        corte = ahora - _VENTANA_MAX
        while _eventos and _eventos[0] < corte:
            _eventos.popleft()


def errores_recientes(minutos: int = 15) -> int:
    corte = datetime.utcnow() - timedelta(minutes=minutos)
    with _lock:
        return sum(1 for t in _eventos if t >= corte)
