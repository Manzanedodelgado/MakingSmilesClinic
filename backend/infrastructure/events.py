"""Bus de eventos en memoria.

`emit` publica un evento para los suscriptores registrados. M00 lo sustituye por
Redis pub/sub (para que funcione con más de un worker); en memoria sirve para
desarrollo y tests. Ningún evento es crítico: emit nunca lanza.
"""
from typing import Any, Callable

_subscribers: dict[str, list[Callable[[dict], None]]] = {}


def subscribe(evento: str, handler: Callable[[dict], None]) -> None:
    _subscribers.setdefault(evento, []).append(handler)


def emit(evento: str, data: dict[str, Any]) -> None:
    for handler in _subscribers.get(evento, []):
        handler(data)
