"""Lectura de portales de proveedor con navegador real (Playwright).

Para facturas que solo están disponibles tras iniciar sesión en el portal del proveedor
(no llegan como adjunto ni como enlace de descarga directo), se abre la página con un
navegador real (Chromium vía Playwright) y se extrae el texto visible y, si la página
sirve directamente un PDF, también sus bytes.

Reutiliza la MISMA guarda anti-SSRF que `gmail_imap.descargar_enlace`
(`gmail_imap._es_destino_privado`), no se reimplementa: una URL que resuelva a una IP no
pública (privada, loopback, link-local, reservada, multicast o sin especificar) nunca
llega a abrir un navegador contra ella.

`sync_playwright` se importa de forma perezosa (dentro de `leer_portal`, no a nivel de
módulo) para que este módulo se pueda importar e inspeccionar aunque el paquete
`playwright` no esté instalado en el entorno (p.ej. en tests que lo mockean por completo).
Se expone como nombre de módulo `sync_playwright` (inicialmente `None`) precisamente para
que los tests puedan parchear `infrastructure.external_apis.portal_browser.sync_playwright`
sin que el paquete real exista.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Optional
from urllib.parse import urljoin, urlparse

from infrastructure.external_apis.gmail_imap import _es_destino_privado

# Nombre de módulo parcheable en tests (`patch("...portal_browser.sync_playwright")`).
# Si sigue siendo None en tiempo de ejecución real, `_sync_playwright()` hace el import
# perezoso del paquete `playwright` de verdad.
sync_playwright = None

MAX_SALTOS_REDIRECCION = 10


def _sync_playwright():
    """Devuelve el `sync_playwright` real (import perezoso) o el que haya sido parcheado."""
    global sync_playwright
    if sync_playwright is not None:
        return sync_playwright
    from playwright.sync_api import sync_playwright as _sp  # import perezoso: puede no estar instalado
    sync_playwright = _sp
    return sync_playwright


def _url_permitida(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if not host:
        return False
    return not _es_destino_privado(host)


def _render(url: str, espera_ms: int) -> dict:
    """Abre `url` en Chromium (Playwright síncrono) y extrae texto/pdf/login.

    Se ejecuta dentro del ThreadPoolExecutor de `leer_portal`, nunca directamente: el
    `sync_playwright` síncrono no se puede lanzar en el hilo principal de un event loop
    (patrón ya usado por `render_js` del script V7)."""
    sp = _sync_playwright()
    pdf_bytes: Optional[bytes] = None

    def _al_recibir_respuesta(response):
        nonlocal pdf_bytes
        if pdf_bytes is not None:
            return
        try:
            ct = (response.headers or {}).get("content-type", "")
        except Exception:  # raiz: cabeceras de la respuesta no inspeccionables -> content-type vacio; no se detecta PDF por cabecera  # noqa: BLE001
            ct = ""
        if "pdf" in ct.lower():
            try:
                pdf_bytes = response.body()
            except Exception:  # raiz: cuerpo de la respuesta no legible -> sin PDF capturado; la lectura del texto continua  # noqa: BLE001
                pass

    def _bloquear_destinos_privados(route):
        """Filtro anti-SSRF de `context.route` para cada petición (navegación, subrecursos,
        fetch/XHR, popups). Las redirecciones se siguen AQUÍ, validando cada salto: si un 3xx
        se entregara al navegador, Chromium seguiría los saltos siguientes sin volver a pasar
        por el route (comprobado con Chromium real: público→público→privado llegaba al
        destino privado)."""
        try:
            url_actual = route.request.url
            if not _url_permitida(url_actual):
                route.abort()
                return
            respuesta = route.fetch(max_redirects=0)
            for _ in range(MAX_SALTOS_REDIRECCION):
                codigo = respuesta.status
                destino = (respuesta.headers or {}).get("location") if 300 <= codigo < 400 else None
                if not destino:
                    route.fulfill(response=respuesta)
                    return
                url_actual = urljoin(url_actual, destino)
                if not _url_permitida(url_actual):
                    route.abort()
                    return
                if codigo in (307, 308):
                    respuesta = contexto.request.fetch(
                        url_actual, method=route.request.method,
                        data=route.request.post_data_buffer, max_redirects=0)
                else:
                    respuesta = contexto.request.fetch(url_actual, method="GET", max_redirects=0)
            route.abort()
        except Exception:  # raiz: peticion interceptada que no se puede inspeccionar no es segura -> se aborta la ruta  # noqa: BLE001
            try:
                route.abort()
            except Exception:  # raiz: abortar la ruta falla (ya abortada/sesion cerrada) -> se ignora; en el interceptor no hay plan B  # noqa: BLE001
                pass

    with sp() as p:
        navegador = p.chromium.launch()
        try:
            # service_workers="block" (C1, ronda 2): un service worker instalado por la
            # página podría interceptar/emitir peticiones de red por su cuenta, sorteando el
            # route del contexto. Se bloquea su registro entero, no solo se filtra tras el
            # hecho.
            contexto = navegador.new_context(service_workers="block")
            # Registrado en el CONTEXTO (no en la página): cubre también popups/
            # `window.open`, que un `page.route` no intercepta (solo la página en la que se
            # registra), además de la página principal y todos sus subrecursos.
            contexto.route("**/*", _bloquear_destinos_privados)
            pagina = contexto.new_page()
            pagina.on("response", _al_recibir_respuesta)
            pagina.goto(url, timeout=espera_ms)
            pagina.wait_for_timeout(min(espera_ms, 2000))
            texto = pagina.inner_text("body") or ""
            requiere_login = pagina.query_selector("input[type=password]") is not None
        finally:
            try:
                navegador.close()
            except Exception:  # raiz: cierre del navegador en finally falla -> se ignora; el resultado ya esta calculado  # noqa: BLE001
                pass
    return {"texto": texto, "pdf_bytes": pdf_bytes, "requiere_login": requiere_login, "error": None}


def leer_portal(url: str, espera_ms: int = 20000) -> dict:
    """Lee un portal de proveedor con un navegador real. Nunca lanza.

    Devuelve siempre {texto, pdf_bytes, requiere_login, error}. Si la URL no pasa la
    guarda anti-SSRF, o si Playwright falla por cualquier motivo (timeout, navegación
    rota, el paquete no instalado, etc.), se devuelve con `error` relleno y sin haber
    abierto ningún navegador (en el caso SSRF) o habiéndolo cerrado de forma segura."""
    vacio = {"texto": "", "pdf_bytes": None, "requiere_login": False, "error": None}
    if not _url_permitida(url):
        return {**vacio, "error": "URL no permitida"}
    # I2 (revisión final de rama): el `executor` NO se crea dentro de un `with` — su
    # `__exit__` llama a `shutdown(wait=True)`, que espera a que `_render` termine aunque
    # `.result()` ya haya saltado por timeout, así que la función no volvía realmente
    # cuando decía que volvía. Se crea suelto y, tras el timeout, se cierra con
    # `wait=False, cancel_futures=True` para no bloquear el retorno.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        futuro = executor.submit(_render, url, espera_ms)
        try:
            resultado = futuro.result(timeout=(espera_ms / 1000.0) + 10)
        except FutureTimeoutError:
            executor.shutdown(wait=False, cancel_futures=True)
            return {**vacio, "error": "Timeout al leer el portal"}
        executor.shutdown(wait=False, cancel_futures=True)
        return resultado
    except Exception as e:  # raiz: cualquier excepcion no prevista de la lectura -> se devuelve error controlado y nunca escapa  # noqa: BLE001
        executor.shutdown(wait=False, cancel_futures=True)
        return {**vacio, "error": str(e)}
