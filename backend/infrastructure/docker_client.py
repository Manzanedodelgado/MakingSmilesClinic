"""Cliente mínimo contra el socket de Docker del host — NUNCA directo: habla por TCP
interno con un `docker-socket-proxy` (Tecnativa, ver docker-compose.yml) que es el único
que monta el socket real.

Alcance REAL del proxy, comprobado a mano contra él (24-jul-2026), no supuesto:
  · permitido : stop / restart / kill de un contenedor (regla fina `ALLOW_RESTARTS`)
  · bloqueado : crear contenedores, arrancarlos, exec, listar, imágenes, volúmenes, red,
                info del sistema → todos 403.
La primera versión de este proxy llevaba `CONTAINERS: 1` creyendo que era "solo lectura de
contenedores"; en realidad es un permiso general sobre /containers que anula las reglas
finas, y dejaba crear + arrancar un contenedor privilegiado con el disco del host montado
(= root en la máquina). Por eso va en 0 — ver el comentario en docker-compose.yml.

Segunda capa, aquí: `ALLOW_RESTARTS` no distingue QUÉ contenedor, así que la lista blanca
de NOMBRE de abajo sigue siendo imprescindible para que Victor solo pueda tocar el que
conocemos, aunque el proxy por sí solo se lo permitiría con cualquiera.
"""
import httpx

from domain.config.settings import settings

# Techo duro — ampliar SOLO por code review, nunca solo desde la config JSON de Centinela
# (que como mucho puede RESTRINGIR esta lista por intersección, nunca ampliarla).
CONTENEDORES_PERMITIDOS = {"makingsmiles-evolution"}


class DockerError(RuntimeError):
    """Fallo al hablar con el docker-socket-proxy, o contenedor fuera de la lista blanca."""


def _cliente() -> httpx.Client:
    return httpx.Client(base_url=settings.docker_proxy_url, timeout=15.0)


def restart_contenedor(nombre: str, whitelist_config: list[str] | None = None) -> dict:
    """Reinicia `nombre` SI está en la intersección de CONTENEDORES_PERMITIDOS (techo duro
    de código) y whitelist_config (si se pasa, restringe más — nunca amplía)."""
    permitidos = CONTENEDORES_PERMITIDOS
    if whitelist_config is not None:
        permitidos = permitidos & set(whitelist_config)
    if nombre not in permitidos:
        raise DockerError(f"Contenedor no permitido: {nombre}")
    try:
        with _cliente() as c:
            r = c.post(f"/containers/{nombre}/restart", params={"t": 10})
    except (httpx.HTTPError, OSError) as e:
        raise DockerError(f"No se pudo hablar con el socket de Docker: {e}") from e
    if r.status_code not in (204, 304):
        raise DockerError(f"restart {nombre} → HTTP {r.status_code}: {r.text[:200]}")
    return {"ok": True, "contenedor": nombre}
