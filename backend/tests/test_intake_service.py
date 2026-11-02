"""Cobertura del orquestador IntakeService sobre SQLite (red/Drive mockeados).

Cubre las rutas que no dependen de servicios externos reales: clasificación, resolución de
factura (con/sin IA), alta de gasto, incidencias, y los buckets A/B/C/D del re-proceso.
"""
from datetime import date
from decimal import Decimal

from application.services import intake_service as mod
from application.services.intake_service import Clasificacion, Fuente, IntakeService, _total_en_texto
from domain.models.gestoria import Gasto

GT = {"proveedor": "SRCL Consenur S.L.U", "cif_emisor": "B86208824",
      "numero_factura": "LGFA2005203", "fecha": "2020-02-10",
      "base_imponible": 102.55, "iva_pct": 21.0, "suplido": 21.33, "total": 145.42}


def _gasto(session, **kw) -> Gasto:
    g = Gasto(centro_id=1, fecha=date(2020, 2, 10), estado="revisar", **kw)
    session.add(g)
    session.commit()
    session.refresh(g)
    return g


def test_clasificar_devuelve_enum(session):
    svc = IntakeService(session, 1)
    assert svc.clasificar({"from": "info@rubiogarciadental.com", "attachments": []}) == Clasificacion.NO_FACTURA


def test_mover_etiqueta_guardada_off(session):
    # Sin INTAKE_MOVER_GMAIL=1 nunca toca el buzón real.
    assert IntakeService(session, 1).mover_etiqueta("12", "Facturas/Incidencias") is False


def test_resolver_factura_sin_ia(session):
    r = IntakeService(session, 1).resolver_factura(Fuente(bytes=b"x"))
    assert r.ok is False and "IA" in (r.error or "")


def test_total_en_texto_formato_espanol():
    assert _total_en_texto(Decimal("1234.56"), "Total a pagar: 1.234,56 €") is True


def test_total_en_texto_formato_punto_decimal():
    assert _total_en_texto(Decimal("145.42"), "TOTAL 145.42") is True


def test_total_en_texto_ausente():
    assert _total_en_texto(Decimal("999.00"), "Total a pagar: 1.234,56 €") is False


def test_total_en_texto_negativo_abono():
    assert _total_en_texto(Decimal("-150.00"), "Importe del abono: -150,00 €") is True


def test_total_en_texto_no_matchea_subcadena_de_total_mayor():
    """Total pequeño que es subcadena de un total mayor presente en el texto NO debe
    dar falso positivo (bug real encontrado en revisión: 34.56 dentro de 1234.56)."""
    assert _total_en_texto(Decimal("34.56"), "Total a pagar: 1234.56 €") is False
    assert _total_en_texto(Decimal("34.56"), "Importe: 34.56€ (IVA incluido)") is True


def test_procesar_mensaje_sin_imap(session):
    assert IntakeService(session, 1).procesar_mensaje("<x>")["ok"] is False


def test_registrar_incidencia_directa(session):
    iid = IntakeService(session, 1).registrar_incidencia(
        "no_factura:test", Fuente(gmail_message_id="<m1>", remitente="a@b.com", asunto="x"))
    assert iid > 0


def test_bucket_b_portal_a_no_factura(session):
    g = _gasto(session, proveedor_extraido='"Endesa Factura"', gmail_message_id="<eb>")
    IntakeService(session, 1).reprocesar_gasto(g.id, "B")
    session.refresh(g)
    assert g.estado == "no_factura" and "endesa" in (g.incidencia or "")


def test_bucket_c_sin_imap_se_queda(session):
    g = _gasto(session, gmail_message_id="<c1>")
    out = IntakeService(session, 1).reprocesar_gasto(g.id, "C")
    assert out["ok"] is False
    session.refresh(g)
    assert g.estado == "revisar"


def test_bucket_d_fuera_de_alcance(session):
    g = _gasto(session)
    out = IntakeService(session, 1).reprocesar_gasto(g.id, "D")
    assert out["ok"] is False


def test_gasto_inexistente(session):
    out = IntakeService(session, 1).reprocesar_gasto(999999, "E")
    assert out["ok"] is False and "no encontrado" in out["error"]


def test_bucket_a_extrae_y_pasa_a_pendiente(session, monkeypatch):
    from application.services.gmail_ingest_service import GmailIngestService
    monkeypatch.setattr(GmailIngestService, "pdf_gasto", lambda self, c, gid: b"%PDF-fake")
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(mod, "extraer_desde_pdf", lambda b, m, llm, aviso=None: dict(GT))
    g = _gasto(session, archivo_pdf_url="https://drive.google.com/file/d/ABC/view")
    IntakeService(session, 1).reprocesar_gasto(g.id, "A")
    session.refresh(g)
    assert g.estado == "pendiente"
    assert g.cif_emisor == "B86208824"
    assert float(g.suplido) == 21.33


def test_resolver_y_registrar_gasto_nuevo(session, monkeypatch):
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(mod, "extraer_desde_pdf", lambda b, m, llm, aviso=None: dict(GT))
    svc = IntakeService(session, 1)
    res = svc.resolver_factura(Fuente(bytes=b"x", gmail_message_id="<n1>"))
    assert res.ok is True
    gid, enlazado = svc.registrar_gasto(res.datos, Fuente(gmail_message_id="<n1>", fecha=date(2020, 2, 10)))
    assert enlazado is False
    g = session.get(Gasto, gid)
    assert g.estado == "pendiente" and g.cif_emisor == "B86208824"
    assert g.suplido == Decimal("21.33")


def test_registrar_gasto_dedup_por_identidad(session, monkeypatch):
    """Una factura con el mismo CIF+nº que otra YA existente (de otra fuente) NO se duplica:
    se enlaza a la existente y se le rellena el gmail_message_id que le faltaba."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(mod, "extraer_desde_pdf", lambda b, m, llm, aviso=None: dict(GT))
    svc = IntakeService(session, 1)
    # Ya existe la misma factura, dada de alta desde una subida de Drive (sin message_id de correo).
    previo = _gasto(session, cif_emisor="B86208824", numero_factura="LGFA2005203",
                    gmail_message_id="upload:drive-123")
    res = svc.resolver_factura(Fuente(bytes=b"x", gmail_message_id="<corr-1>"))
    gid, enlazado = svc.registrar_gasto(res.datos, Fuente(gmail_message_id="<corr-1>",
                                                          fecha=date(2020, 2, 10)))
    assert enlazado is True
    assert gid == previo.id                                   # misma fila, no una nueva
    assert session.exec(mod.select(Gasto).where(Gasto.centro_id == 1)).all().__len__() == 1
    session.refresh(previo)
    assert previo.gmail_message_id == "<corr-1>"              # se enlazó el correo
    assert previo.estado == "revisar"                         # no se crea fila nueva ni se pisa la existente


def test_dedup_sin_cif_por_numero_y_total(session):
    """El correo 'Pagada'/recordatorio de una factura ya registrada suele venir SIN CIF: debe
    deduplicarse por nº + total exacto (era el hueco que duplicaba). Total distinto NO casa."""
    svc = IntakeService(session, 1)
    previo = _gasto(session, cif_emisor="B86208824", numero_factura="LGFA2005203", total=Decimal("145.42"))
    g = svc._buscar_por_identidad({"cif": None, "numero_factura": "LGFA2005203", "total": 145.42})
    assert g is not None and g.id == previo.id
    assert svc._buscar_por_identidad({"cif": None, "numero_factura": "LGFA2005203", "total": 999.0}) is None
    assert svc._buscar_por_identidad({"cif": None, "numero_factura": "", "total": 145.42}) is None


def test_leer_sin_adjunto_del_cuerpo(session, monkeypatch):
    """Factura sin adjunto pero escrita en el CUERPO del correo → se lee igualmente (vía 'cuerpo')."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(mod, "extraer_desde_texto", lambda texto, llm, aviso=None: dict(GT))
    svc = IntakeService(session, 1)
    email = {"enlaces": [], "cuerpo": "Factura LGFA2005203 total 145,42€"}
    fuente = Fuente(gmail_message_id="<b1>")
    res = svc._leer_sin_adjunto(email, fuente)
    assert res.ok is True and fuente.origen == "cuerpo"


def test_leer_sin_adjunto_del_enlace(session, monkeypatch):
    """Aviso de portal con enlace directo a PDF → se descarga y se lee (vía 'enlace')."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(mod, "extraer_desde_pdf", lambda b, m, llm, aviso=None: dict(GT))
    monkeypatch.setattr(mod.gmail_imap, "descargar_enlace",
                        lambda url: {"content": b"%PDF-fake", "content_type": "application/pdf", "filename": "f.pdf"})
    svc = IntakeService(session, 1)
    email = {"enlaces": ["https://portal.example.com/factura/123.pdf"], "cuerpo": ""}
    fuente = Fuente(gmail_message_id="<e1>")
    res = svc._leer_sin_adjunto(email, fuente)
    assert res.ok is True and fuente.origen == "enlace"


def test_leer_sin_adjunto_enlace_html_se_descarta(session, monkeypatch):
    """Un enlace que devuelve HTML (login del portal), no un PDF, NO se toma como factura."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(mod.gmail_imap, "descargar_enlace",
                        lambda url: {"content": b"<html>login</html>", "content_type": "text/html", "filename": "x"})
    svc = IntakeService(session, 1)
    email = {"enlaces": ["https://portal.example.com/login"], "cuerpo": ""}
    res = svc._leer_sin_adjunto(email, Fuente(gmail_message_id="<h1>"))
    assert res.ok is False


def test_leer_sin_adjunto_via_portal_con_js(session, monkeypatch):
    """Enlace que devuelve HTML (no PDF directo) pero el navegador real sí consigue el PDF."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(mod.gmail_imap, "descargar_enlace",
                        lambda url: {"content": b"<html>cargando...</html>", "content_type": "text/html", "filename": "x"})
    monkeypatch.setattr(mod, "leer_portal", lambda url, **kw: {"texto": "", "pdf_bytes": b"%PDF-fake",
                                                                "requiere_login": False, "error": None})
    monkeypatch.setattr(mod, "extraer_desde_pdf", lambda b, m, llm, aviso=None: dict(GT))
    svc = IntakeService(session, 1)
    email = {"enlaces": ["https://portal.example.com/factura/123"], "cuerpo": ""}
    res = svc._leer_sin_adjunto(email, Fuente(gmail_message_id="<p1>"))
    assert res.ok is True and res.datos["cif"] == "B86208824"


def test_resolver_factura_corrige_en_varias_rondas(session, monkeypatch):
    """El validador rechaza las 2 primeras respuestas (CIF del receptor) y acepta la 3ª:
    debe reintentar más de una vez, no rendirse tras el primer reintento."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    intentos = {"n": 0}
    malo = {**GT, "cif_emisor": "B88393764"}       # CIF de la propia clínica: inválido
    def fake_extraer(b, m, llm, aviso=None):
        intentos["n"] += 1
        return dict(GT) if intentos["n"] >= 3 else dict(malo)
    monkeypatch.setattr(mod, "extraer_desde_pdf", fake_extraer)
    res = IntakeService(session, 1).resolver_factura(Fuente(bytes=b"x"))
    assert res.ok is True
    assert intentos["n"] == 3


def test_resolver_factura_agota_rondas_y_devuelve_incidencia(session, monkeypatch):
    """Si el validador sigue rechazando tras MAX_RONDAS_CORRECCION intentos, se devuelve la
    última Resolucion (incidencia), sin excepción ni bucle infinito."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    malo = {**GT, "cif_emisor": "B88393764"}
    monkeypatch.setattr(mod, "extraer_desde_pdf", lambda b, m, llm, aviso=None: dict(malo))
    res = IntakeService(session, 1).resolver_factura(Fuente(bytes=b"x"))
    assert res.ok is False


def test_resolver_factura_cif_extranjero_no_insiste_en_reintentar(session, monkeypatch):
    """normalizar_cif ya acepta CIF extranjeros (VAT/EIN). Si la extracción viene con uno
    válido de ese tipo, _feedback_reintento no debe forzar una ronda extra solo por no ser
    un CIF español: el chequeo de 'cif ausente o del receptor' es sobre el VALOR, no el formato."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    extranjero = {**GT, "cif_emisor": "US123456789"}   # EIN de EEUU, formato ya normalizado
    intentos = {"n": 0}
    def fake_extraer(b, m, llm, aviso=None):
        intentos["n"] += 1
        return dict(extranjero)
    monkeypatch.setattr(mod, "extraer_desde_pdf", fake_extraer)
    res = IntakeService(session, 1).resolver_factura(Fuente(bytes=b"x"))
    assert res.ok is True
    assert intentos["n"] == 1   # aceptado a la primera, sin rondas de más


# ───────────────────────── I1: _total_en_texto en el camino de PDF ─────────────────────────

def test_resolver_factura_adjunto_pasa_texto_fuente_del_pdf(session, monkeypatch):
    """I1 (revisión final de rama): procesar_mensaje con FACTURA por ADJUNTO debe pasar
    texto_fuente a resolver_factura usando el pdf_texto ya extraído por gmail_imap (y el
    cuerpo), no "" — si el total que devuelve la IA no está en ese texto, se rechaza."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(IntakeService, "_clasificar_detalle",
                        lambda self, email: (Clasificacion.FACTURA, "test"))
    monkeypatch.setattr(IntakeService, "mover_etiqueta", lambda self, *a, **kw: False)
    # La IA "inventa" un total (999.99) que NO aparece en el texto del PDF ni del correo.
    # El suplido se ajusta para que base+IVA-suplido siga siendo ARITMÉTICAMENTE coherente
    # (mismo ratio de IVA que el caso real, ~21%): así el validador NO lo rechaza por
    # 'iva_incoherente' antes de llegar al chequeo de total_literal que este test ejercita.
    inventado = {**GT, "total": 999.99, "suplido": 875.90}
    monkeypatch.setattr(mod, "extraer_desde_pdf", lambda b, m, llm, aviso=None: dict(inventado))
    # Mock de _pdf_text (I1, ronda 2): el texto REAL del PDF no contiene el total inventado.
    monkeypatch.setattr(mod.gmail_imap, "_pdf_text", lambda b: "TOTAL A PAGAR: 145,42 EUR")
    svc = IntakeService(session, 1)
    email = {"uid": "1", "msg_id": "<adj1>", "cuerpo": "Factura adjunta, ver PDF.",
            "adjuntos": [{"content": b"%PDF-fake", "content_type": "application/pdf"}],
            "enlaces": []}
    fuente = Fuente(gmail_message_id="<adj1>")
    fuente.bytes = email["adjuntos"][0]["content"]
    fuente.mime = email["adjuntos"][0]["content_type"]
    fuente.origen = "adjunto"
    res = svc.resolver_factura(fuente, texto_fuente=mod._texto_fuente_pdf(fuente.bytes, email))
    assert res.ok is False
    assert "total_no_literal_en_texto" in (res.incidencias or [])


def test_resolver_factura_enlace_total_solo_en_pdf_no_en_cuerpo_se_acepta(session, monkeypatch):
    """I1 — REGRESIÓN detectada por el re-revisor en la ronda 1: una factura real que llega
    por ENLACE/PORTAL, donde el total aparece en el PDF pero NO en el cuerpo del correo (el
    caso normal: "Su factura está disponible, ver adjunto"), debe seguir ACEPTÁNDOSE. Mi
    fix de la ronda 1 usaba solo el cuerpo del correo como texto_fuente en estos caminos —
    eso rechazaba facturas válidas por total_no_literal_en_texto. Aquí se verifica que,
    usando el texto REAL del PDF (gmail_imap._pdf_text), el chequeo encuentra el total y
    la factura se acepta a la primera, sin agotar rondas."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(mod.gmail_imap, "descargar_enlace",
                        lambda url: {"content": b"%PDF-fake", "content_type": "application/pdf", "filename": "f.pdf"})
    # El total SOLO está en el texto real del PDF, NUNCA en el cuerpo del correo.
    monkeypatch.setattr(mod.gmail_imap, "_pdf_text", lambda b: "TOTAL A PAGAR: 145,42 EUR")
    intentos = {"n": 0}
    def fake_extraer(b, m, llm, aviso=None):
        intentos["n"] += 1
        return dict(GT)
    monkeypatch.setattr(mod, "extraer_desde_pdf", fake_extraer)
    svc = IntakeService(session, 1)
    email = {"enlaces": ["https://portal.example.com/factura/1.pdf"],
            "cuerpo": "Su factura está disponible, ver adjunto."}   # el cuerpo NO lleva el total
    fuente = Fuente(gmail_message_id="<e2>")
    res = svc._leer_sin_adjunto(email, fuente)
    assert res.ok is True
    assert intentos["n"] == 1   # aceptada a la primera: el total SÍ se encontró (en el PDF)


def test_texto_fuente_pdf_combina_texto_real_del_pdf_y_cuerpo(monkeypatch):
    """I1 (ronda 2): el helper que construye texto_fuente para los caminos de PDF debe
    incluir TANTO el texto real extraído del PDF (gmail_imap._pdf_text) como el cuerpo del
    correo — no solo uno de los dos."""
    monkeypatch.setattr(mod.gmail_imap, "_pdf_text", lambda b: "TOTAL: 145,42 €")
    email = {"cuerpo": "Ver adjunto.", "pdf_texto": "ignorado"}
    texto = mod._texto_fuente_pdf(b"%PDF-fake", email)
    assert "Ver adjunto" in texto and "145,42" in texto


def test_texto_fuente_pdf_sin_capa_de_texto_devuelve_vacio_no_el_cuerpo(monkeypatch):
    """I1 (re-revisión ronda 3 — corrige un hueco real de la ronda 2): si el PDF es una
    imagen escaneada/foto SIN capa de texto (_pdf_text devuelve ""), _texto_fuente_pdf debe
    devolver "" DIRECTAMENTE — NO el cuerpo del correo como sustituto. El cuerpo nunca
    contiene el total real de una factura escaneada; usarlo como texto_fuente aplicaba el
    chequeo de total literal sobre un texto que estructuralmente no puede contener el
    total, rechazando por error facturas legítimas de proveedores que escanean/fotografían.
    "" real = el chequeo se salta en _validar_datos (comportamiento seguro)."""
    monkeypatch.setattr(mod.gmail_imap, "_pdf_text", lambda b: "")   # PDF sin capa de texto
    email = {"cuerpo": "Factura adjunta, gracias.", "pdf_texto": ""}
    texto = mod._texto_fuente_pdf(b"%PDF-fake-escaneado", email)
    assert texto == ""


def test_texto_fuente_pdf_sin_capa_de_texto_con_bytes_no_pdf_tambien_vacio():
    """Mismo caso pero con _pdf_text real (sin mockear): bytes que no son un PDF válido
    también dan "" de _pdf_text, y el resultado debe seguir siendo "" (no el cuerpo)."""
    email = {"cuerpo": "Factura adjunta.", "pdf_texto": ""}
    texto = mod._texto_fuente_pdf(b"no es un pdf real", email)
    assert texto == ""


def test_resolver_factura_escaneada_sin_texto_se_acepta_con_ocr_de_imagen(session, monkeypatch):
    """I1 — caso exacto pedido por el re-revisor: un PDF escaneado/foto SIN capa de texto
    (_pdf_text devuelve ""), con un correo tipo "Factura adjunta, gracias" (sin el total),
    debe seguir ACEPTÁNDOSE si el resto de los datos son válidos (CIF, proveedor, total
    extraídos por OCR de imagen, la vía real para este tipo de documento) — el chequeo de
    total literal no debe bloquear este caso porque no hay texto fiable del documento
    contra el que comprobar nada."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(mod.gmail_imap, "_pdf_text", lambda b: "")   # escaneado: sin capa de texto
    monkeypatch.setattr(mod, "extraer_desde_pdf", lambda b, m, llm, aviso=None: dict(GT))
    svc = IntakeService(session, 1)
    email = {"cuerpo": "Factura adjunta, gracias.", "adjuntos": [
        {"content": b"%PDF-escaneado", "content_type": "application/pdf"}]}
    fuente = Fuente(gmail_message_id="<esc1>", bytes=b"%PDF-escaneado", mime="application/pdf",
                    origen="adjunto")
    res = svc.resolver_factura(fuente, texto_fuente=mod._texto_fuente_pdf(fuente.bytes, email))
    assert res.ok is True


def test_texto_fuente_pdf_vacio_si_no_hay_nada():
    assert mod._texto_fuente_pdf(b"") == ""
    assert mod._texto_fuente_pdf(b"", None) == ""


def test_texto_fuente_email_combina_cuerpo_y_pdf_texto():
    """El helper _texto_fuente_email (usado por _texto_fuente_pdf internamente) sigue
    incluyendo cuerpo + pdf_texto ya extraído por gmail_imap._parse_message."""
    email = {"cuerpo": "Ver adjunto.", "pdf_texto": "TOTAL: 145,42 €"}
    texto = mod._texto_fuente_email(email)
    assert "Ver adjunto" in texto and "145,42" in texto


def test_texto_fuente_email_vacio_si_no_hay_nada():
    assert mod._texto_fuente_email({}) == ""


# I2 (timeout real de leer_portal) está cubierto en test_portal_browser.py, junto al resto
# de tests de ese módulo.


# ───────────────────────── I3: fuente contaminada tras PDF descartado ─────────────────────────

def test_leer_sin_adjunto_portal_pdf_invalido_no_contamina_fuente(session, monkeypatch):
    """I3: si el PDF que trae el portal NO valida (continue), fuente.bytes/mime/origen deben
    quedar como estaban ANTES de ese intento — si gana el cuerpo del correo después, no debe
    archivarse el PDF descartado contra el gasto equivocado."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(mod.gmail_imap, "descargar_enlace",
                        lambda url: {"content": b"<html>cargando...</html>", "content_type": "text/html", "filename": "x"})
    monkeypatch.setattr(mod, "leer_portal", lambda url, **kw: {"texto": "", "pdf_bytes": b"%PDF-otro",
                                                                "requiere_login": False, "error": None})
    # El PDF del portal NUNCA valida (total inventado); el cuerpo del correo SÍ es la factura real.
    malo_portal = {**GT, "total": 999.99}
    respuestas = iter([dict(malo_portal)] * 4 + [dict(GT)])
    monkeypatch.setattr(mod, "extraer_desde_pdf", lambda b, m, llm, aviso=None: next(respuestas))
    monkeypatch.setattr(mod, "extraer_desde_texto", lambda texto, llm, aviso=None: dict(GT))
    svc = IntakeService(session, 1)
    fuente = Fuente(gmail_message_id="<i3>", bytes=b"", mime="application/pdf", origen="drive")
    email = {"enlaces": ["https://portal.example.com/factura/1"],
            "cuerpo": "Factura LGFA2005203 total 145,42€"}
    res = svc._leer_sin_adjunto(email, fuente)
    assert res.ok is True
    assert fuente.origen == "cuerpo"
    # El PDF descartado del portal NO debe seguir en fuente.bytes tras ganar el cuerpo.
    assert fuente.bytes != b"%PDF-otro"
    assert fuente.bytes == b""


# ───────────────────────── I4: no reintentar en la 1ª ronda sin NINGÚN dato ─────────────────────────

def test_resolver_factura_pagina_basura_sin_datos_no_agota_rondas(session, monkeypatch):
    """I4: si la 1ª ronda no trae NINGÚN total y NINGÚN CIF (ambos completamente vacíos,
    no solo inválidos), no debe reintentar — no hay nada que una ronda adicional pueda
    corregir en un banner de cookies o una landing sin factura."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    intentos = {"n": 0}
    vacio = {"proveedor": None, "cif_emisor": None, "numero_factura": None,
            "fecha": None, "base_imponible": None, "iva_pct": None, "suplido": None, "total": None}
    def fake_extraer(b, m, llm, aviso=None):
        intentos["n"] += 1
        return dict(vacio)
    monkeypatch.setattr(mod, "extraer_desde_pdf", fake_extraer)
    res = IntakeService(session, 1).resolver_factura(Fuente(bytes=b"x"))
    assert res.ok is False
    assert intentos["n"] == 1   # ni un reintento de más: no hay nada que corregir


def test_resolver_factura_dato_parcial_si_reintenta(session, monkeypatch):
    """I4 no debe romper el caso real que SÍ debe reintentar: hay un CIF (aunque inválido,
    el de la propia clínica) en la 1ª ronda, así que sigue siendo 'dato parcialmente mal
    leído', no 'esto no es una factura' — debe seguir reintentando como antes."""
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    intentos = {"n": 0}
    malo = {**GT, "cif_emisor": "B88393764"}
    def fake_extraer(b, m, llm, aviso=None):
        intentos["n"] += 1
        return dict(GT) if intentos["n"] >= 2 else dict(malo)
    monkeypatch.setattr(mod, "extraer_desde_pdf", fake_extraer)
    res = IntakeService(session, 1).resolver_factura(Fuente(bytes=b"x"))
    assert res.ok is True
    assert intentos["n"] == 2


# ───────────────────────── I5: formatos adicionales de _total_en_texto ─────────────────────────

def test_total_en_texto_sin_decimales():
    assert _total_en_texto(Decimal("50.00"), "Total: 50 €") is True


def test_total_en_texto_coma_guion():
    assert _total_en_texto(Decimal("50.00"), "Importe: 50,- EUR") is True


def test_total_en_texto_separador_miles_espacio():
    assert _total_en_texto(Decimal("1234.56"), "Total a pagar: 1 234,56 €") is True


def test_total_en_texto_dolar_miles_coma_decimal_punto():
    assert _total_en_texto(Decimal("1234.56"), "Amount due: $1,234.56") is True


def test_total_en_texto_un_solo_decimal():
    assert _total_en_texto(Decimal("145.40"), "Total: 145,4 €") is True
    assert _total_en_texto(Decimal("145.40"), "Total: 145.4") is True


# I5 — regresión Alta detectada por el re-revisor en la ronda 1: la variante en-US de
# miles (f"{int(parte_entera):,}") no llevaba la parte decimal de vuelta, así que para
# cualquier total menor de 1000 (sin separador de miles) la variante equivalía solo a la
# parte ENTERA, sin exigir que el número terminase ahí — casi anulaba el chequeo.

def test_total_en_texto_no_matchea_con_porcentaje_de_dos_cifras():
    """12.30 NO debe matchear contra "IVA 12% total 300,00" por el "12" suelto del 12%."""
    assert _total_en_texto(Decimal("12.30"), "IVA 12% total 300,00") is False


def test_total_en_texto_no_matchea_con_total_de_decimales_distintos():
    """145.42 NO debe matchear contra "Total 145,99 EUR" (mismos 3 primeros dígitos,
    decimales distintos: son importes DIFERENTES)."""
    assert _total_en_texto(Decimal("145.42"), "Total 145,99 EUR") is False


def test_total_en_texto_no_matchea_con_numero_suelto_sin_decimales():
    """145.42 NO debe matchear contra "Pedido 145 unidades" (el "145" sin más no es el
    total real, que SÍ tiene céntimos: 145.42 ≠ 145)."""
    assert _total_en_texto(Decimal("145.42"), "Pedido 145 unidades") is False


def test_total_en_texto_dolar_miles_no_matchea_decimales_distintos():
    """1234.56 NO debe matchear contra "$1,234.99" (mismos miles, céntimos distintos)."""
    assert _total_en_texto(Decimal("1234.56"), "$1,234.99") is False


# Los 5 formatos que SÍ se arreglaron en la ronda 1 deben seguir dando True tras la
# corrección de la ronda 2 — no se rompen de nuevo.

def test_total_en_texto_ronda1_formatos_siguen_funcionando():
    assert _total_en_texto(Decimal("50.00"), "Total: 50 €") is True
    assert _total_en_texto(Decimal("50.00"), "Importe: 50,- EUR") is True
    assert _total_en_texto(Decimal("1234.56"), "Total a pagar: 1 234,56 €") is True
    assert _total_en_texto(Decimal("1234.56"), "Amount due: $1,234.56") is True
    assert _total_en_texto(Decimal("145.40"), "Total: 145,4 €") is True
    assert _total_en_texto(Decimal("145.40"), "Total: 145.4") is True


def test_total_en_texto_no_matchea_cola_de_numero_con_miles():
    """145,42 no debe darse por bueno si el texto dice 1.145,42 (otro importe)."""
    assert _total_en_texto(Decimal("145.42"), "Total factura: 1.145,42 €") is False
    assert _total_en_texto(Decimal("234.56"), "Amount due: $1,234.56") is False
    assert _total_en_texto(Decimal("1145.42"), "Total factura: 1.145,42 €") is True


def test_total_en_texto_tabla_con_importes_separados_por_espacio():
    """Las tablas de factura ponen importes seguidos separados por espacio: el total
    no debe rechazarse por ir detrás de otro número."""
    assert _total_en_texto(Decimal("121.00"), "Base IVA Total 100,00 21,00 121,00") is True


def _incidencia(session, motivo, msgid="<inc-1>"):
    from domain.models.gestoria import GastoIncidencia
    i = GastoIncidencia(centro_id=1, gmail_message_id=msgid, fecha=date(2020, 2, 10),
                        remitente="facturas@consenur.es", asunto="Factura", motivo=motivo)
    session.add(i)
    session.commit()
    session.refresh(i)
    return i


def _preparar_reintento(monkeypatch, datos=GT, movidos=None):
    monkeypatch.setattr(IntakeService, "_imap_cfg", lambda self: {"usuario": "x"})
    monkeypatch.setattr(IntakeService, "_llm_cfg", lambda self: {"base_url": "x", "model": "y"})
    monkeypatch.setattr(IntakeService, "_clasificar_detalle", lambda self, email: (Clasificacion.FACTURA, ""))
    monkeypatch.setattr(IntakeService, "_archivar", lambda self, gid, email, fuente: None)
    monkeypatch.setattr(IntakeService, "mover_etiqueta",
                        lambda self, uid, etiqueta, origen=None: (movidos.append(etiqueta) if movidos is not None else None) or True)
    monkeypatch.setattr(mod.gmail_imap, "fetch_por_message_id",
                        lambda cfg, mid, carpeta=None: {"uid": "7", "remitente": "facturas@consenur.es", "asunto": "Factura",
                                                        "cuerpo": "", "adjuntos": [{"content": b"%PDF-fake", "content_type": "application/pdf"}]})
    monkeypatch.setattr(mod, "extraer_desde_pdf", lambda b, m, llm, aviso=None: dict(datos) if datos else {})


def test_reintentar_incidencias_simulacion_no_escribe(session, monkeypatch):
    from domain.models.gestoria import GastoIncidencia
    _preparar_reintento(monkeypatch)
    inc = _incidencia(session, "factura_no_legible:etapa2_estructura: Chat falló tras 4 intentos: HTTP 429")
    res = IntakeService(session, 1).reintentar_incidencias(throttle=0)
    assert res["recuperables"] == 1 and res["recuperadas"] == 1
    assert session.exec(mod.select(Gasto)).all() == []
    assert session.get(GastoIncidencia, inc.id) is not None


def test_reintentar_incidencias_ejecuta_registra_y_limpia(session, monkeypatch):
    from domain.models.gestoria import GastoIncidencia
    movidos = []
    _preparar_reintento(monkeypatch, movidos=movidos)
    inc = _incidencia(session, "ia_descarte:ia_http404:No endpoints found")
    res = IntakeService(session, 1).reintentar_incidencias(execute=True, throttle=0)
    assert res["recuperadas"] == 1
    g = session.exec(mod.select(Gasto)).one()
    assert g.cif_emisor == "B86208824" and g.gmail_message_id == "<inc-1>"
    assert session.get(GastoIncidencia, inc.id) is None
    assert movidos == [mod.ETIQUETA_PROCESADAS]


def test_reintentar_incidencias_ignora_motivos_no_recuperables(session, monkeypatch):
    _preparar_reintento(monkeypatch)
    _incidencia(session, "no_factura:no_parece_factura")
    _incidencia(session, "falta_documento:portal:endesa", msgid="<inc-2>")
    res = IntakeService(session, 1).reintentar_incidencias(execute=True, throttle=0)
    assert res["recuperables"] == 0 and res["procesadas"] == 0
    assert session.exec(mod.select(Gasto)).all() == []


def test_reintentar_incidencias_si_sigue_mal_se_queda_con_motivo_nuevo(session, monkeypatch):
    from domain.models.gestoria import GastoIncidencia
    _preparar_reintento(monkeypatch, datos={**GT, "cif_emisor": None, "total": None})
    inc = _incidencia(session, "factura_no_legible:sin_datos")
    res = IntakeService(session, 1).reintentar_incidencias(execute=True, throttle=0)
    assert res["siguenMal"] == 1 and res["recuperadas"] == 0
    session.refresh(inc)
    assert session.get(GastoIncidencia, inc.id) is not None
    assert inc.motivo.startswith("factura_no_legible:")
    assert session.exec(mod.select(Gasto)).all() == []


def test_registrar_gasto_cierra_las_incidencias_del_mismo_correo(session):
    from domain.models.gestoria import GastoIncidencia
    inc = _incidencia(session, "factura_no_legible:sin_datos", msgid="<m-reg>")
    otra = _incidencia(session, "factura_no_legible:sin_datos", msgid="<otro>")
    IntakeService(session, 1).registrar_gasto(dict(GT), Fuente(gmail_message_id="<m-reg>"))
    assert session.get(GastoIncidencia, inc.id) is None
    assert session.get(GastoIncidencia, otra.id) is not None


def test_reintentar_incidencias_huerfana_con_gasto_se_cierra_sin_ia(session, monkeypatch):
    from domain.models.gestoria import GastoIncidencia
    _preparar_reintento(monkeypatch)
    session.add(Gasto(centro_id=1, fecha=date(2020, 2, 10), gmail_message_id="<inc-1>"))
    session.commit()
    inc = _incidencia(session, "factura_no_legible:sin_datos")

    def _no_imap(*a, **k):
        raise AssertionError("una huérfana no debe tocar Gmail ni la IA")
    monkeypatch.setattr(mod.gmail_imap, "fetch_por_message_id", _no_imap)
    svc = IntakeService(session, 1)
    res = svc.reintentar_incidencias(throttle=0)
    assert res["yaConGasto"] == 1 and res["errores"] == 0
    assert session.get(GastoIncidencia, inc.id) is not None  # simulación: no borra
    res = svc.reintentar_incidencias(execute=True, throttle=0)
    assert res["yaConGasto"] == 1
    assert session.get(GastoIncidencia, inc.id) is None
    assert len(session.exec(mod.select(Gasto)).all()) == 1


def test_reintentar_incidencias_busca_tambien_en_procesados(session, monkeypatch):
    from domain.models.gestoria import GastoIncidencia
    movidos = []
    _preparar_reintento(monkeypatch, movidos=movidos)
    buscadas = []
    email = {"uid": "7", "remitente": "facturas@consenur.es", "asunto": "Factura", "cuerpo": "",
             "adjuntos": [{"content": b"%PDF-fake", "content_type": "application/pdf"}]}

    def _fetch(cfg, mid, carpeta=None):
        buscadas.append(carpeta)
        return email if carpeta == mod.ETIQUETA_PROCESADAS else None
    monkeypatch.setattr(mod.gmail_imap, "fetch_por_message_id", _fetch)
    inc = _incidencia(session, "factura_no_legible:sin_datos")
    res = IntakeService(session, 1).reintentar_incidencias(execute=True, throttle=0)
    assert buscadas == [mod.ETIQUETA_INCIDENCIAS, mod.ETIQUETA_PROCESADAS]
    assert res["recuperadas"] == 1 and res["noEncontradas"] == 0
    assert session.get(GastoIncidencia, inc.id) is None
    assert movidos == []  # ya estaba en Procesados: no se mueve


# ───────── rescate del emisor cuando SOLO falla el CIF (prueba de 200 correos, 27-oct-2026) ─────────

def _datos_sin_cif(proveedor, total=121.0, base=100.0, iva=21.0):
    return {"proveedor": proveedor, "cif_emisor": None, "numero_factura": "F-1", "fecha": "2026-10-01",
            "base_imponible": base, "iva_pct": iva, "total": total}


def test_rescate_cif_de_proveedor_conocido(session):
    from domain.models.gestoria import Proveedor
    session.add(Proveedor(centro_id=1, nombre="Implant Protesis Dental 2004, S.L.", cif="B86208824"))
    session.commit()
    res = IntakeService(session, 1)._validar_datos(_datos_sin_cif("IMPLANT PROTESIS DENTAL 2004 SL"),
                                                    "Total factura 121,00 €")
    assert res.ok and res.datos["cif"] == "B86208824"
    assert res.datos["cif_origen"] == "proveedor_conocido"


def test_rescate_no_elige_si_el_proveedor_tiene_dos_cifs(session):
    session.add(Gasto(centro_id=1, fecha=date(2026, 1, 1), proveedor_extraido="Acme SL", cif_emisor="B86208824"))
    session.add(Gasto(centro_id=1, fecha=date(2026, 1, 2), proveedor_extraido="ACME, S.L.", cif_emisor="B85937787"))
    session.commit()
    res = IntakeService(session, 1)._validar_datos(_datos_sin_cif("Acme SL"), "Total 121,00")
    assert not res.ok


def test_rescate_recibo_extranjero_sin_id_fiscal(session):
    res = IntakeService(session, 1)._validar_datos(
        _datos_sin_cif("MOONSHOT AI PTE. LTD.", total=39.0, base=39.0, iva=0.0),
        "Receipt from MOONSHOT AI PTE. LTD.\nAmount paid $39.00\nPaid October 1, 2026")
    assert res.ok and res.datos["cif"] is None
    assert res.datos["cif_origen"] == "extranjero_sin_id_fiscal"


def test_rescate_nunca_da_a_la_clinica_como_proveedor(session):
    res = IntakeService(session, 1)._validar_datos(
        _datos_sin_cif("TRIDENTAL ODONTOLOGOS SLP", total=39.0, base=39.0, iva=0.0), "Receipt $39.00")
    assert not res.ok


def test_rescate_exige_texto_del_documento(session):
    """Sin texto fuente no hay forma de comprobar el total: no se rescata."""
    res = IntakeService(session, 1)._validar_datos(
        _datos_sin_cif("MOONSHOT AI PTE. LTD.", total=39.0, base=39.0, iva=0.0), "")
    assert not res.ok


def test_rescate_recibo_con_total_que_no_esta_en_el_texto(session):
    res = IntakeService(session, 1)._validar_datos(
        _datos_sin_cif("MOONSHOT AI PTE. LTD.", total=49.0, base=49.0, iva=0.0), "Receipt Amount paid $39.00")
    assert not res.ok


def test_motor_fiscal_lee_el_numero_de_factura():
    """La purga del 5-sep-2026 borró _ROTULOS_NUMERO y el motor fallaba en TODAS las facturas."""
    from domain.services import gestor_lectura_fiscal as fiscal
    assert fiscal.numero_factura("FACTURA Nº FV-2026/118\nFecha 01/10/2026") is not None


def test_total_es_subtotal_de_pagina_dentix():
    texto = "ASPIRADORES 2,00 4,10\nSUMA Y SIGUE 977,44\nPÁG 2\nSUMA ANTERIOR 977,44\nTOTAL FRA 1.367,91€"
    assert mod._total_es_subtotal(Decimal("977.44"), texto) is True
    assert mod._total_es_subtotal(Decimal("1367.91"), texto) is False


def test_total_es_base_turset_y_no_dispara_si_el_rotulo_lee_la_base():
    turset = "Base IVA 344,23 IVA 21,00 72,29\nImporte líquido (EUR) 416,52\nVencimientos 416,52"
    assert mod._total_es_base(Decimal("344.23"), turset) == Decimal("416.52")
    assert mod._total_es_base(Decimal("416.52"), turset) is None
    servicopy = "BASE IMPONIBLE 5,93\nIVA 21% 1,25\nTOTAL 7,18"
    assert mod._total_es_base(Decimal("7.18"), servicopy) is None


def test_validar_rechaza_subtotal_y_el_feedback_lo_explica(session):
    svc = IntakeService(session, 1)
    datos = {"proveedor": "Dentix", "cif_emisor": "B85937787", "numero_factura": "A 2601867",
             "fecha": "2026-07-29", "base_imponible": 807.80, "iva_pct": 21.0, "total": 977.44}
    texto = "SUMA Y SIGUE 977,44\nSUMA ANTERIOR 977,44\nTOTAL FRA 1.367,91"
    res = svc._validar_datos(datos, texto)
    assert not res.ok and "total_es_subtotal_de_pagina" in res.incidencias
    assert "SUMA Y SIGUE" in svc._feedback_reintento(res, texto)


# ───────── piezas del script V7 portadas al lector de producción ─────────

def test_pista_identificadores_excluye_clinica_y_administradores():
    from application.services.extract_service import pista_identificadores
    texto = "Emisor IMPLANT PROTESIS CIF B63568513\nCliente TRIDENTAL B88393764\nAdmin 52982664W\nVAT No: IE3668997OH"
    p = pista_identificadores(texto)
    assert "B63568513" in p and "B88393764" not in p and "52982664W" not in p
    assert "IE3668997OH" in p or "3668997" in p


def test_rescate_aeat_como_organismo_publico(session):
    res = IntakeService(session, 1)._validar_datos(
        _datos_sin_cif("AGENCIA ESTATAL DE ADMINISTRACION TRIBUTARIA", total=1814.31, base=1814.31, iva=0.0),
        "Modelo 115 importe a ingresar 1.814,31")
    assert res.ok and res.datos["cif"] == "Q2826000H"


def test_irpf_llega_al_validador_y_la_factura_cuadra(session):
    datos = {"proveedor": "Colaborador", "cif_emisor": "B86208824", "numero_factura": "7", "fecha": "2026-10-01",
             "base_imponible": 1000.0, "iva_pct": 0.0, "irpf": 150.0, "total": 850.0}
    res = IntakeService(session, 1)._validar_datos(datos, "Total a pagar 850,00")
    assert res.ok, res.incidencias


def test_aviso_total_no_literal_lista_los_importes_del_documento(session):
    svc = IntakeService(session, 1)
    res = mod.Resolucion(ok=False, datos={"cif": "B86208824", "total": 99.0}, incidencias=["total_no_literal_en_texto"])
    fb = svc._feedback_reintento(res, "Base 100,00 IVA 21,00 Total 121,00")
    assert "121,00" in fb


def test_descartado_por_la_ia_sin_importe_no_es_incidencia(session):
    res = IntakeService(session, 1)._validar_datos(
        {"accion": "descartado", "motivo_descarte": "propuesta de prácticas", "total": None}, "Propuesta")
    assert not res.ok and res.incidencias == ["descartado_ia:propuesta de prácticas"]
    assert IntakeService(session, 1)._feedback_reintento(res, "Propuesta") is None


def test_descartado_con_importe_no_se_descarta(session):
    datos = {"accion": "descartado", "proveedor": "Consenur", "cif_emisor": "B86208824", "numero_factura": "1",
             "fecha": "2026-10-01", "base_imponible": 100.0, "iva_pct": 21.0, "total": 121.0}
    res = IntakeService(session, 1)._validar_datos(datos, "Total 121,00")
    assert res.ok


def test_total_corregido_por_cuadre_culligan(session):
    texto = "Base Imponible 1.72€ 9.91€ 1.72€ Total 0.00€ 8.19€ 0.00€ CIF B-06304984"
    datos = {"proveedor": "CULLIGAN WATER SPAIN SL", "cif_emisor": "B86208824", "numero_factura": "4625679",
             "fecha": "2026-09-30", "base_imponible": 8.19, "iva_pct": 21.0, "total": 11.63}
    res = IntakeService(session, 1)._validar_datos(datos, texto)
    assert res.ok and res.datos["total"] == 9.91


def test_cuadre_no_inventa_si_la_base_no_esta_en_el_documento(session):
    datos = {"proveedor": "X", "cif_emisor": "B86208824", "numero_factura": "1", "fecha": "2026-09-30",
             "base_imponible": 8.20, "iva_pct": 21.0, "total": 11.63}
    res = IntakeService(session, 1)._validar_datos(datos, "Total 9,92")
    assert not res.ok and res.datos["total"] == 11.63 and not res.datos.get("total_corregido_por_cuadre")


def test_correo_que_dice_factura_no_se_descarta_aunque_la_ia_lo_diga():
    res = mod.Resolucion(ok=False, datos={}, incidencias=["descartado_ia:aviso de pago"])
    out = mod._proteger_facturas_del_descarte(res, {"asunto": "Factura F20263955 de KOKUAI S.L."})
    assert out.incidencias == ["factura_no_legible:ia_dice_no_gasto:aviso de pago"]
    otro = mod._proteger_facturas_del_descarte(res, {"asunto": "CERTIFICADO DIGITAL DE LA SOCIEDAD"})
    assert otro.incidencias == ["descartado_ia:aviso de pago"]


# ───────── errores del reintento real del 27-oct-2026 (gastos 4985 y 4987, divisa) ─────────

def test_aeat_no_se_rescata_si_el_documento_trae_otro_cif(session):
    res = IntakeService(session, 1)._validar_datos(
        _datos_sin_cif("Agencia Tributaria", total=5.84, base=4.83, iva=21.0),
        "COMERCIAL SERVICOPY S.L. CIF B86208824 Factura 2026-7470 Total 5,84")
    assert not res.ok


def test_proveedor_conocido_no_se_rescata_si_el_documento_trae_otro_cif(session):
    from domain.models.gestoria import Proveedor
    session.add(Proveedor(centro_id=1, nombre="Agencia Tributaria", cif="Q2826000H"))
    session.commit()
    res = IntakeService(session, 1)._validar_datos(
        _datos_sin_cif("Agencia Tributaria", total=5.84, base=4.83, iva=21.0),
        "Emisor CIF B86208824 Total 5,84")
    assert not res.ok


def test_proveedor_con_nombre_de_la_clinica_es_incidencia(session):
    datos = {"proveedor": "TRIDENTAL ODONTOLOGOS S.L.P.", "cif_emisor": "B86208824", "numero_factura": "10248",
             "fecha": "2026-08-04", "base_imponible": 90.0, "iva_pct": 10.0, "total": 99.0}
    res = IntakeService(session, 1)._validar_datos(datos, "Total 99,00")
    assert not res.ok and "proveedor_es_clinica" in res.incidencias


def test_la_divisa_se_guarda_en_el_gasto(session):
    svc = IntakeService(session, 1)
    g = Gasto(centro_id=1, fecha=date(2026, 9, 3))
    svc._volcar_datos(g, {"total": 9.9, "divisa": "USD"})
    assert g.divisa == "USD"
