"""Relleno de los consentimientos COEM (PDF) por ESTAMPADO con PyMuPDF (fitz).

Los PDF COEM son fijos (sin campos de formulario). Estampamos sobre ellos:
  - Pág. 1: Clínica dental, Dr./Dra., Colegiado nº.
  - Pág. 2 (izquierda): "Yo, {paciente}, mayor de edad y con DNI nº {dni}".
  - Pág. 2 (bloque PACIENTE, derecha): fecha y — al firmar — la firma manuscrita.
Las posiciones se localizan por ANCLAJE de texto (search_for), así valen para las 9
plantillas (comparten maquetación COEM). Origen fitz = esquina superior izquierda.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

import base64
import io
from typing import Optional

import fitz  # PyMuPDF

_AZUL = (0.08, 0.22, 0.5)
_MESES = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _put(page, x, y, txt, size=9):
    if txt:
        page.insert_text((x, y), str(txt), fontsize=size, color=_AZUL, fontname="helv")


def _put_fit(page, x, y, txt, maxw, size=8):
    """Como _put pero encoge la fuente hasta que el texto quepa en `maxw` puntos."""
    if not txt:
        return
    s = size
    while s > 5 and fitz.get_text_length(str(txt), fontname="helv", fontsize=s) > maxw:
        s -= 0.5
    page.insert_text((x, y), str(txt), fontsize=s, color=_AZUL, fontname="helv")


def _primer(rects, key=lambda r: r.y0):
    return sorted(rects, key=key)[0] if rects else None


def _fecha(page, ciudad, dia, mes, anio):
    """Rellena la 1ª línea de fecha 'En {ciudad} a {dia} de {mes} de 20{anio}' del bloque derecho."""
    words = page.get_text("words")   # (x0, y0, x1, y1, texto, …)
    # Columna derecha: el "En…a" arranca en ~x437-449 (odontopediatría 437.8, resto 449.3);
    # la columna izquierda acaba en ~x410, así que 420 la separa bien.
    enrow = sorted(
        [w for w in words if w[0] > 420 and w[4].startswith("En") and w[4].rstrip().endswith("a")],
        key=lambda w: w[1],
    )
    if not enrow:
        return
    ew = enrow[0]
    base = ew[3] - 1.5
    fila = sorted([w for w in words if abs(w[1] - ew[1]) < 3 and w[0] > 420], key=lambda w: w[0])
    _put_fit(page, ew[0] + 22, base, ciudad, maxw=ew[2] - ew[0] - 26, size=8)   # tras "En", antes de "a"
    if len(fila) >= 2:
        _put(page, fila[1][0] + 2, base, dia, 8)          # campo del día
    if len(fila) >= 3:
        _put(page, fila[2][0] + 12, base, mes, 8)         # tras el primer "de"
    if len(fila) >= 4:
        _put(page, fila[3][0] + 12, base, anio, 8)        # tras "20"


def rellenar_consentimiento(
    template_path: str,
    *,
    clinica: str = "",
    doctor: str = "",
    colegiado: str = "",
    paciente: str = "",
    dni: str = "",
    ciudad: str = "",
    dia: str = "",
    mes: str = "",
    anio: str = "",
    firma_png: Optional[bytes] = None,
    firma_profesional_png: Optional[bytes] = None,
) -> bytes:
    """Devuelve los bytes del PDF COEM relleno. `firma_png` = firma manuscrita del PACIENTE
    (al firmar); `firma_profesional_png` = firma del COLABORADOR que realiza (de Config →
    Colaboradores), pre-estampada sobre el hueco 'El/la facultativo/a'."""
    doc = fitz.open(template_path)
    p1, p2 = doc[0], doc[1]

    # ── Pág. 1 · cabecera ──
    cl = _primer(p1.search_for("Clínica dental"))
    if cl:
        _put(p1, cl.x1 + 8, cl.y1 - 2, clinica)
        _put(p1, cl.x1 + 8, cl.y1 + 27, doctor)          # línea Dr./Dra. (~+29)
    co = _primer(p1.search_for("Colegiado"))
    if co:
        _put(p1, co.x1 + 24, co.y1 - 2, colegiado)

    # ── Pág. 2 · relleno según layout (estándar adulto vs. odontopediatría/menor) ──
    if p2.search_for("Nombre del paciente"):
        # Odontopediatría: el paciente es menor y firma su representante (datos que NO tenemos).
        # Rellenamos SOLO lo conocido: nombre del paciente, facultativo y fecha; el nombre/DNI del
        # representante se dejan en blanco para cumplimentar a mano (no estampamos al menor ahí).
        npac = _primer(p2.search_for("Nombre del paciente"))
        if npac:
            _put(p2, npac.x1 + 6, npac.y1, paciente)
    else:
        # Preámbulo izquierda: "Yo, {paciente} … mayor de edad y con DNI nº {dni}"
        yo = _primer(p2.search_for("Yo,"))
        if yo:
            _put(p2, yo.x1 + 6, yo.y1, paciente)
        dnil = _primer([r for r in p2.search_for("DNI n") if r.x0 < 430])
        if dnil:
            _put(p2, dnil.x1 + 6, dnil.y1, dni)
        # Bloque PACIENTE (derecha): "D. / Dª {paciente} … con DNI {dni}"
        cd = _primer([r for r in p2.search_for("con DNI") if r.x0 > 540])   # topmost = PACIENTE
        if cd:
            yb = cd.y1 - 1.5
            _put_fit(p2, 567, yb, paciente, maxw=cd.x0 - 567 - 4, size=8)
            _put(p2, cd.x1 + 6, yb, dni, 8)

    # Facultativo (común): "declaro que el/la facultativo/a, Dr/Dra {doctor}"
    dr = _primer([r for r in p2.search_for("Dr/Dra") if r.x0 > 440])
    if dr:
        _put_fit(p2, dr.x1 + 4, dr.y1 - 1.5, doctor, maxw=250, size=8)

    # Fecha (común): "En {ciudad} a {dia} de {mes} de 20{anio}"
    _fecha(p2, ciudad, dia, mes, anio)

    # ── Pág. 2 · firma (encima de "Firmado, el/la paciente") ──
    if firma_png:
        fir = _primer([r for r in p2.search_for("Firmado, el/la paciente") if r.x0 > 540])
        if fir:
            rect = fitz.Rect(fir.x0 - 5, fir.y0 - 26, fir.x0 + 90, fir.y0 - 3)
            p2.insert_image(rect, stream=firma_png, keep_proportion=True, overlay=True)

    # ── Firma del PROFESIONAL (colaborador que realiza), sobre la línea "Firma, nº de colegiado"
    #    del bloque FACULTATIVO (espejo de donde firma el paciente). ──
    if firma_profesional_png:
        fac = _primer(p2.search_for("Firma, n"))
        if fac:
            rect = fitz.Rect(fac.x0, fac.y0 - 30, fac.x0 + 120, fac.y0 - 4)
            p2.insert_image(rect, stream=firma_profesional_png, keep_proportion=True, overlay=True)

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


def incrustar_firma(pdf_path: str, firma_png: bytes) -> bytes:
    """Estampa la firma manuscrita en el PDF ya generado (sobre 'Firmado, el/la paciente')."""
    doc = fitz.open(pdf_path)
    p2 = doc[1]
    fir = _primer([r for r in p2.search_for("Firmado, el/la paciente") if r.x0 > 540])
    if fir:
        rect = fitz.Rect(fir.x0 - 5, fir.y0 - 26, fir.x0 + 90, fir.y0 - 3)
        p2.insert_image(rect, stream=firma_png, keep_proportion=True, overlay=True)
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


def fecha_partes(iso_o_date) -> tuple[str, str, str]:
    """(dia, mes_nombre, anio_2dig) desde 'YYYY-MM-DD' o date/datetime."""
    from datetime import date, datetime
    if isinstance(iso_o_date, str):
        d = datetime.fromisoformat(iso_o_date[:10]).date()
    elif isinstance(iso_o_date, datetime):
        d = iso_o_date.date()
    elif isinstance(iso_o_date, date):
        d = iso_o_date
    else:
        return "", "", ""
    return str(d.day), _MESES[d.month], f"{d.year % 100:02d}"


def firma_desde_datauri(datauri: str) -> Optional[bytes]:
    """Convierte 'data:image/png;base64,...' en bytes; None si no válido."""
    if not datauri or "," not in datauri:
        return None
    try:
        return base64.b64decode(datauri.split(",", 1)[1])
    except Exception:
        return None
