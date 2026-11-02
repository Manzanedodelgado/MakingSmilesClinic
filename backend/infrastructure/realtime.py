"""Bus de eventos para tiempo real (SSE) — Redis pub/sub con fallback a memoria.

Por qué Redis: el bus anterior era pub/sub en memoria dentro de UN proceso uvicorn.
En cuanto hubiera 2+ workers, un evento publicado en el worker A no llegaba a los
clientes SSE conectados al worker B — fallo silencioso e intermitente. Redis pub/sub
lo resuelve (todos los workers publican/escuchan el mismo canal) y además sobrevive a
reinicios del backend.

Contrato público (NO cambiar sin tocar todos los consumidores):
  - ``await bus.subscribe(centro_id) -> asyncio.Queue``   (cola local del suscriptor)
  - ``bus.unsubscribe(centro_id, queue)``
  - ``bus.publish(centro_id, evento: dict)``              (seguro desde threadpool)
  - ``bus.bind_loop(loop)``                               (en el lifespan)
  - ``await bus.connect()`` / ``await bus.aclose()``      (lifespan; no-op sin Redis)

Cada suscriptor recibe una ``asyncio.Queue`` local. Un único task de fondo por proceso
escucha TODOS los canales ``centro:*`` de Redis y reparte a las colas locales del
centro correspondiente. Si ``settings.redis_url`` está vacío o Redis no responde al
arrancar, el bus funciona solo en memoria (dev local), con la limitación de 1 worker.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from domain.config.settings import settings

logger = logging.getLogger("organismo.bus")

_CANAL_PREFIJO = "centro:"


async def _cerrar_quieto(coro, que: str) -> None:
    """Cierre best-effort en apagado: si ya cayó (incluida cancelación), nada que cerrar."""
    try:
        await coro
    except (asyncio.CancelledError, Exception):  # raiz: en apagado no hay plan B
        logger.debug("Bus: cierre de %s", que, exc_info=True)


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._redis: Any = None          # redis.asyncio.Redis | None
        self._pubsub_task: Optional[asyncio.Task] = None
        self._modo_redis = False

    # ── ciclo de vida ────────────────────────────────────────────────
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Se llama al arrancar (lifespan), ya dentro del event loop."""
        self._loop = loop

    async def connect(self) -> None:
        """Conecta a Redis y arranca el escuchador. No-op si no hay REDIS_URL.
        Si Redis está configurado pero no responde, cae a modo memoria (no rompe el arranque)."""
        url = (settings.redis_url or "").strip()
        if not url:
            logger.info("Bus de eventos: modo MEMORIA (sin REDIS_URL; 1 worker).")
            return
        try:
            import redis.asyncio as aioredis  # type: ignore

            self._redis = aioredis.from_url(url, decode_responses=True)
            await self._redis.ping()
            self._pubsub_task = asyncio.create_task(self._escuchar_redis(), name="event-bus-redis")
            self._modo_redis = True
            logger.info("Bus de eventos: modo REDIS pub/sub (%s).", url)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Bus de eventos: REDIS_URL definido pero Redis no responde (%s). "
                "Fallback a modo MEMORIA (1 worker).", exc,
            )
            self._redis = None
            self._modo_redis = False

    async def aclose(self) -> None:
        if self._pubsub_task:
            self._pubsub_task.cancel()
            await _cerrar_quieto(self._pubsub_task, "tarea pubsub")
            self._pubsub_task = None
        if self._redis is not None:
            await _cerrar_quieto(self._redis.aclose(), "Redis")
            self._redis = None
        self._modo_redis = False

    async def _escuchar_redis(self) -> None:
        """Task de fondo: escucha `centro:*` en Redis y reparte a las colas locales."""
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(f"{_CANAL_PREFIJO}*")
        try:
            async for msg in pubsub.listen():
                if msg is None or msg.get("type") != "pmessage":
                    continue
                canal = msg.get("channel", "")
                try:
                    centro_id = int(str(canal).split(":", 1)[1])
                    evento = json.loads(msg["data"])
                except (ValueError, IndexError, KeyError, json.JSONDecodeError):
                    continue
                self._repartir_local(centro_id, evento)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bus Redis: escuchador caido (%s). Tiempo real degradado a memoria.", exc)
        finally:
            await _cerrar_quieto(pubsub.aclose(), "pubsub")

    # ── API de suscripción (idéntica a la versión en memoria) ────────
    async def subscribe(self, centro_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs.setdefault(centro_id, set()).add(q)
        return q

    def unsubscribe(self, centro_id: int, q: asyncio.Queue) -> None:
        subs = self._subs.get(centro_id)
        if subs:
            subs.discard(q)
            if not subs:
                self._subs.pop(centro_id, None)

    # ── publicación ─────────────────────────────────────────────────
    def publish(self, centro_id: int, evento: dict[str, Any]) -> None:
        """Publica un evento para el centro. Seguro de llamar desde el threadpool
        (endpoints síncronos) o desde el event loop."""
        if self._modo_redis and self._redis is not None and self._loop is not None:
            # Redis: publicar de forma thread-safe en el loop.
            self._loop.call_soon_threadsafe(self._publish_redis, centro_id, evento)
        else:
            # Memoria: reparto directo a las colas locales.
            loop = self._loop
            if loop is None:
                return
            loop.call_soon_threadsafe(self._repartir_local, centro_id, evento)

    def _publish_redis(self, centro_id: int, evento: dict[str, Any]) -> None:
        assert self._redis is not None
        canal = f"{_CANAL_PREFIJO}{centro_id}"
        asyncio.create_task(self._redis.publish(canal, json.dumps(evento)))

    def _repartir_local(self, centro_id: int, evento: dict[str, Any]) -> None:
        for q in list(self._subs.get(centro_id, ())):
            self._poner(q, evento)

    @staticmethod
    def _poner(q: asyncio.Queue, evento: dict[str, Any]) -> None:
        try:
            q.put_nowait(evento)
        except asyncio.QueueFull:
            pass  # cliente lento: se descarta; el refetch al (re)conectar lo corrige

    def suscriptores(self, centro_id: int) -> int:
        return len(self._subs.get(centro_id, ()))


bus = EventBus()
