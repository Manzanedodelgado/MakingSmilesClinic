"""Debounce de respuesta por conversación (un único proceso uvicorn, mismo patrón que
`infrastructure/realtime.py`): agrupa varios mensajes entrantes seguidos del mismo
paciente en un solo turno para Alex, en vez de responder a cada fragmento por separado.

Disparo ÚNICO por ráfaga: se arma al llegar un mensaje y se reemplaza (nunca se acumula)
si llega otro antes de disparar. No hay temporizador que se re-arme por silencio del
paciente — si nadie vuelve a escribir, el callback dispara una sola vez y no queda nada
pendiente. No implementa reintentos ni recordatorios.
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional


class Debouncer:
    def __init__(self) -> None:
        self._pendientes: dict[int, asyncio.TimerHandle] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Se llama al arrancar (lifespan), ya dentro del event loop."""
        self._loop = loop

    def programar(self, conv_id: int, espera_seg: float, callback: Callable[[], None]) -> None:
        """Reemplaza cualquier disparo pendiente de esta conversación por uno nuevo dentro
        de `espera_seg`. El callback (síncrono: DB + LLM + envío) corre en el threadpool,
        no en el event loop, para no bloquear el resto de la app mientras Alex "piensa"."""
        self.cancelar(conv_id)
        if self._loop is None:
            return

        def _disparar() -> None:
            self._pendientes.pop(conv_id, None)
            self._loop.run_in_executor(None, callback)  # type: ignore[union-attr]

        self._pendientes[conv_id] = self._loop.call_later(espera_seg, _disparar)

    def cancelar(self, conv_id: int) -> None:
        h = self._pendientes.pop(conv_id, None)
        if h:
            h.cancel()

    def pendiente(self, conv_id: int) -> bool:
        return conv_id in self._pendientes


debouncer = Debouncer()
