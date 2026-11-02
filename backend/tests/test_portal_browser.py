"""Tests de `leer_portal` (lectura de portales de proveedor con navegador real).

Playwright se mockea por completo: estos tests no requieren que el paquete `playwright`
ni Chromium estén instalados de verdad, solo que `portal_browser.py` lo importe de forma
perezosa (dentro de la función) para poder parchear `sync_playwright` a nivel de módulo.
"""
import time
from unittest.mock import MagicMock, patch

from infrastructure.external_apis.portal_browser import leer_portal


def test_leer_portal_url_no_publica_no_abre_navegador():
    resultado = leer_portal("http://192.168.1.1/factura")
    assert resultado["error"] is not None
    assert resultado["pdf_bytes"] is None


def _instalar_playwright_mock(monkeypatch, texto="contenido normal", password=False):
    """Instala un mock completo de sync_playwright → navegador → contexto → página, con la
    cadena new_context()/new_page() que usa `_render` tras la ronda 2 del fix (C1:
    contexto.route en vez de pagina.route). Devuelve (navegador, contexto, pagina) para que
    cada test pueda inspeccionar las llamadas que le interesan. Usa monkeypatch.setattr (no
    unittest.mock.patch().start()) para que la limpieza sea automática al final del test."""
    pagina = MagicMock()
    pagina.query_selector.return_value = MagicMock() if password else None
    pagina.inner_text.return_value = texto
    contexto = MagicMock()
    contexto.new_page.return_value = pagina
    navegador = MagicMock()
    navegador.new_context.return_value = contexto
    playwright_cm = MagicMock()
    playwright_cm.chromium.launch.return_value = navegador
    mock_sp = MagicMock()
    mock_sp.return_value.__enter__.return_value = playwright_cm
    import infrastructure.external_apis.portal_browser as pb
    monkeypatch.setattr(pb, "sync_playwright", mock_sp)
    return navegador, contexto, pagina


def test_leer_portal_detecta_login(monkeypatch):
    """Mock de sync_playwright: query_selector('input[type=password]') devuelve un elemento
    (hay login), inner_text('body') devuelve texto corto, no hay respuestas con content-type pdf.

    `portal.example.com` es un host de prueba ficticio que no resuelve por DNS real, así
    que se mockea también la guarda anti-SSRF (`_es_destino_privado`, la misma que usa
    `gmail_imap.descargar_enlace`) para aislar lo que este test verifica de verdad: la
    detección de login vía Playwright, no la resolución DNS en vivo de un dominio inventado
    (que ya cubre `test_leer_portal_url_no_publica_no_abre_navegador` con una IP privada,
    sin depender de DNS)."""
    _instalar_playwright_mock(monkeypatch, texto="Inicia sesión para ver tu factura", password=True)
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", return_value=False):
        resultado = leer_portal("https://portal.example.com/factura/1")
    assert resultado["requiere_login"] is True
    assert resultado["pdf_bytes"] is None


def test_leer_portal_timeout_no_bloquea_en_shutdown(monkeypatch):
    """I2 (revisión final de rama): si _render tarda más que el timeout, leer_portal debe
    devolver 'Timeout al leer el portal' SIN esperar a que _render termine — antes, el
    `with ThreadPoolExecutor` llamaba a shutdown(wait=True) en su __exit__ y el timeout no
    tenía ningún efecto real (la función solo volvía cuando _render terminaba, tardase lo
    que tardase)."""
    import infrastructure.external_apis.portal_browser as pb

    # leer_portal espera futuro.result(timeout=(espera_ms/1000) + 10) → con espera_ms=100,
    # el timeout real es 10.1s. _render debe tardar MÁS que eso para que salte el timeout;
    # se sustituye _render por uno que duerme 20s, muy por encima, y se comprueba que
    # leer_portal vuelve mucho antes (en torno a los 10.1s del timeout), no a los 20s.
    def _render_lento(url, espera_ms):
        time.sleep(20)
        return {"texto": "tarde", "pdf_bytes": None, "requiere_login": False, "error": None}

    monkeypatch.setattr(pb, "_render", _render_lento)
    monkeypatch.setattr(pb, "_url_permitida", lambda url: True)
    inicio = time.monotonic()
    resultado = pb.leer_portal("https://proveedor.example.com/factura", espera_ms=100)
    duracion = time.monotonic() - inicio
    assert resultado["error"] == "Timeout al leer el portal"
    # Debe volver cerca del timeout real (~10.1s), no esperar los 20s de _render_lento.
    assert duracion < 15


def _handler_registrado(contexto):
    """Extrae (patrón, handler) del primer context.route(...) registrado por _render."""
    assert contexto.route.called
    patron, handler = contexto.route.call_args[0]
    return patron, handler


def test_render_registra_handler_en_el_contexto_no_en_la_pagina(monkeypatch):
    """C1 (re-revisión, ronda 2): el handler anti-SSRF debe registrarse en el CONTEXTO
    (`context.route`), no en la página (`page.route`) — así cubre también popups/
    `window.open`, que un page.route no intercepta (solo la página en la que se registra).
    Además, el contexto debe crearse con service_workers="block" (un service worker podría
    emitir peticiones de red sin pasar por el route del contexto).

    Playwright no está instalado en este entorno de test: se mockea `sync_playwright` por
    completo. Esto confirma que el código REGISTRA el handler en el sitio correcto y con la
    config correcta — no confirma el comportamiento real de red de Chromium, que requeriría
    el paquete instalado (riesgo documentado: no verificado end-to-end)."""
    import infrastructure.external_apis.portal_browser as pb
    navegador, contexto, pagina = _instalar_playwright_mock(monkeypatch)
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", return_value=False):
        pb._render("https://portal.example.com/factura/1", espera_ms=1000)

    navegador.new_context.assert_called_once_with(service_workers="block")
    patron, _ = _handler_registrado(contexto)
    assert patron == "**/*"
    assert not pagina.route.called   # NO se registra en la página: solo en el contexto


def _route_mock(url, status=200, location=None):
    route = MagicMock()
    route.request.url = url
    respuesta = MagicMock()
    respuesta.status = status
    respuesta.headers = {"location": location} if location else {}
    route.fetch.return_value = respuesta
    return route, respuesta


def test_handler_anti_ssrf_url_inicial_privada_aborta_sin_fetch(monkeypatch):
    """Si la URL inicial de la petición ya es un destino privado, se aborta de inmediato —
    ni siquiera se llega a hacer el fetch real."""
    import infrastructure.external_apis.portal_browser as pb
    _, contexto, _ = _instalar_playwright_mock(monkeypatch)
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", return_value=False):
        pb._render("https://portal.example.com/factura/1", espera_ms=1000)
    _, handler = _handler_registrado(contexto)

    route, _ = _route_mock("http://169.254.169.254/latest/meta-data/")
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", return_value=True):
        handler(route)
    route.abort.assert_called_once()
    route.fetch.assert_not_called()
    route.fulfill.assert_not_called()


def test_handler_anti_ssrf_url_publica_sin_redireccion_se_sirve(monkeypatch):
    """URL pública que responde 200 directamente: se hace el fetch real con max_redirects=0
    y se sirve esa respuesta con route.fulfill (no un continue_ simple: el handler controla
    la petición)."""
    import infrastructure.external_apis.portal_browser as pb
    _, contexto, _ = _instalar_playwright_mock(monkeypatch)
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", return_value=False):
        pb._render("https://portal.example.com/factura/1", espera_ms=1000)
    _, handler = _handler_registrado(contexto)

    route, respuesta = _route_mock("https://proveedor-real.example.com/factura.pdf", status=200)
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", return_value=False):
        handler(route)
    route.fetch.assert_called_once_with(max_redirects=0)
    route.fulfill.assert_called_once_with(response=respuesta)
    route.abort.assert_not_called()


def test_handler_anti_ssrf_redireccion_a_destino_privado_se_aborta(monkeypatch):
    """C1 — el vector real que motivó este hallazgo, corregido en ronda 3: una URL pública
    que responde con un 30x cuyo Location apunta a un destino privado (p.ej. 127.0.0.1, el
    escenario exacto en el que descargar_enlace ya rechaza la URL y Task 5 reabre con
    leer_portal). El mock de route.fetch simula el comportamiento REAL de Playwright con
    max_redirects=0: devuelve el 302 CON su Location SIN seguirlo — a diferencia de la
    ronda 2, donde el mock simulaba (incorrectamente) que fetch() ya había seguido saltos.
    El handler debe inspeccionar ese Location y abortar sin servir la respuesta ni llamar a
    fetch() una segunda vez (no sigue la redirección él mismo: la rechaza antes de que el
    navegador la vea)."""
    import infrastructure.external_apis.portal_browser as pb
    _, contexto, _ = _instalar_playwright_mock(monkeypatch)
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", return_value=False):
        pb._render("https://portal.example.com/factura/1", espera_ms=1000)
    _, handler = _handler_registrado(contexto)

    route, _ = _route_mock("https://proveedor-real.example.com/factura.pdf",
                           status=302, location="http://127.0.0.1:8080/admin")

    def _privado(host):
        return host in ("127.0.0.1",)   # la URL inicial es pública; la redirigida, no
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", side_effect=_privado):
        handler(route)
    route.fetch.assert_called_once_with(max_redirects=0)   # UN solo fetch, no se sigue manualmente
    route.abort.assert_called_once()
    route.fulfill.assert_not_called()


def _respuesta(status=200, location=None):
    r = MagicMock()
    r.status = status
    r.headers = {"location": location} if location else {}
    return r


def _preparar_handler(monkeypatch):
    import infrastructure.external_apis.portal_browser as pb
    _, contexto, _ = _instalar_playwright_mock(monkeypatch)
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", return_value=False):
        pb._render("https://portal.example.com/factura/1", espera_ms=1000)
    _, handler = _handler_registrado(contexto)
    return contexto, handler


def test_handler_anti_ssrf_redireccion_publica_se_sigue_y_sirve_el_destino(monkeypatch):
    """A (pública) -> 302 -> B (pública) -> 200: el handler sigue el salto él mismo y sirve
    la respuesta final; nunca entrega el 3xx al navegador."""
    contexto, handler = _preparar_handler(monkeypatch)
    route, _ = _route_mock("https://proveedor.example.com/f.pdf", status=302,
                           location="https://cdn.proveedor.example.com/f.pdf")
    final = _respuesta(200)
    contexto.request.fetch.return_value = final
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", return_value=False):
        handler(route)
    contexto.request.fetch.assert_called_once_with(
        "https://cdn.proveedor.example.com/f.pdf", method="GET", max_redirects=0)
    route.fulfill.assert_called_once_with(response=final)
    route.abort.assert_not_called()


def test_handler_anti_ssrf_cadena_publica_publica_privada_se_aborta(monkeypatch):
    """Vector encontrado con Chromium real: A (pública) -> B (pública) -> C (privada).
    El salto a C se rechaza antes de pedirlo y no se sirve nada."""
    contexto, handler = _preparar_handler(monkeypatch)
    route, _ = _route_mock("https://a.example.com/f", status=302, location="https://b.example.com/f")
    contexto.request.fetch.return_value = _respuesta(302, location="http://10.0.0.5/interno")
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado",
               side_effect=lambda host: host == "10.0.0.5"):
        handler(route)
    contexto.request.fetch.assert_called_once()   # se pidió B, nunca C
    route.abort.assert_called_once()
    route.fulfill.assert_not_called()


def test_handler_anti_ssrf_demasiados_saltos_se_aborta(monkeypatch):
    """Un bucle de redirecciones entre hosts públicos no se sigue indefinidamente."""
    import infrastructure.external_apis.portal_browser as pb
    contexto, handler = _preparar_handler(monkeypatch)
    route, _ = _route_mock("https://a.example.com/f", status=302, location="https://a.example.com/f")
    contexto.request.fetch.return_value = _respuesta(302, location="https://a.example.com/f")
    with patch("infrastructure.external_apis.portal_browser._es_destino_privado", return_value=False):
        handler(route)
    assert contexto.request.fetch.call_count == pb.MAX_SALTOS_REDIRECCION
    route.abort.assert_called_once()
    route.fulfill.assert_not_called()
