"""Informe cefalométrico en PDF (PyMuPDF/fitz).

Compone una página A4 con: cabecera (paciente + análisis + fecha), la telerradiografía con los
landmarks y algunas líneas de referencia sobrepuestas a escala, la tabla de medidas comparadas con
la norma (color por desviación) y la interpretación. Determinista; el trazado ya viene calculado.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

from datetime import date
from typing import Optional

import fitz  # PyMuPDF

_AZUL = (0x01 / 255, 0x3b / 255, 0x82 / 255)
_TEAL = (0x1c / 255, 0xa0 / 255, 0xd1 / 255)
_GRIS = (0.45, 0.45, 0.45)
_VERDE = (0.05, 0.6, 0.3)
_AMBAR = (0.72, 0.53, 0.04)
_ROJO = (0.73, 0.11, 0.11)

# Líneas de referencia a dibujar si sus dos extremos existen (por análisis).
_LINEAS = {
    "steiner": [("S", "N"), ("N", "A"), ("N", "B"), ("Go", "Gn")],
    "ricketts": [("Po", "Or"), ("N", "Pog"), ("A", "Pog"), ("Go", "Me")],
}


def _color_desv(desv: Optional[float], sd: Optional[float]):
    if desv is None or sd is None or sd == 0:
        return _AZUL
    z = abs(desv) / sd
    return _VERDE if z <= 1 else (_AMBAR if z <= 2 else _ROJO)


def informe_pdf(*, imagen_bytes: bytes, analisis_label: str, analisis: str,
                landmarks: dict, mediciones: dict, interpretacion: dict,
                paciente: str, num_historia: str, calibrada: bool) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    M = 40

    # Cabecera
    page.insert_text((M, 50), "Informe cefalométrico", fontsize=18, color=_AZUL, fontname="hebo")
    page.insert_text((M, 70), f"Análisis de {analisis_label}", fontsize=11, color=_TEAL, fontname="helv")
    page.insert_text((M, 90), f"Paciente: {paciente}   ·   Nº historia: {num_historia}", fontsize=10, color=_GRIS, fontname="helv")
    page.insert_text((M, 104), f"Fecha: {date.today().strftime('%d/%m/%Y')}", fontsize=10, color=_GRIS, fontname="helv")
    page.draw_line(fitz.Point(M, 114), fitz.Point(595 - M, 114), color=_TEAL, width=1)

    # Imagen con overlay (mitad superior)
    destino = fitz.Rect(M, 128, 595 - M, 468)
    try:
        pix = fitz.Pixmap(imagen_bytes)
        iw, ih = pix.width, pix.height
    except Exception:  # raiz: imagen ilegible -> sin escala; el PDF sale sin esa imagen
        iw, ih = 0, 0
    if iw and ih:
        escala = min(destino.width / iw, destino.height / ih)
        dw, dh = iw * escala, ih * escala
        x0 = destino.x0 + (destino.width - dw) / 2
        y0 = destino.y0
        img_rect = fitz.Rect(x0, y0, x0 + dw, y0 + dh)
        page.insert_image(img_rect, stream=imagen_bytes, keep_proportion=True)

        def punto(code: str):
            p = landmarks.get(code)
            if not p:
                return None
            return fitz.Point(x0 + float(p[0]) * escala, y0 + float(p[1]) * escala)

        for a, b in _LINEAS.get(analisis, []):
            pa, pb = punto(a), punto(b)
            if pa and pb:
                page.draw_line(pa, pb, color=_TEAL, width=0.8)
        for code in landmarks:
            pt = punto(code)
            if pt:
                page.draw_circle(pt, 2.4, color=(1, 1, 1), fill=_AZUL, width=0.4)
                page.insert_text((pt.x + 4, pt.y + 3), code, fontsize=6.5, color=_TEAL, fontname="helv")

    # Tabla de medidas
    y = 500
    page.insert_text((M, y), "Medida", fontsize=9, color=_GRIS, fontname="hebo")
    page.insert_text((M + 230, y), "Valor", fontsize=9, color=_GRIS, fontname="hebo")
    page.insert_text((M + 300, y), "Norma", fontsize=9, color=_GRIS, fontname="hebo")
    page.insert_text((M + 370, y), "Desv.", fontsize=9, color=_GRIS, fontname="hebo")
    y += 6
    page.draw_line(fitz.Point(M, y), fitz.Point(595 - M, y), color=(0.85, 0.85, 0.85), width=0.5)
    y += 14
    for m in mediciones.values():
        unidad = m.get("unidad", "")
        valor = m.get("valor")
        norma = m.get("norma")
        sd = m.get("sd")
        desv = m.get("desviacion")
        page.insert_text((M, y), str(m.get("label", "")), fontsize=9, color=(0.2, 0.2, 0.2), fontname="helv")
        page.insert_text((M + 230, y), f"{valor}{unidad}" if valor is not None else "—",
                         fontsize=9, color=_color_desv(desv, sd), fontname="hebo")
        page.insert_text((M + 300, y), (f"{norma}±{sd}" if norma is not None else ""), fontsize=8.5, color=_GRIS, fontname="helv")
        page.insert_text((M + 370, y), (f"{desv:+.1f}" if desv is not None else ""), fontsize=8.5, color=_color_desv(desv, sd), fontname="helv")
        y += 15

    if not calibrada:
        y += 4
        page.insert_text((M, y), "Sin calibración: las medidas en mm no se muestran.", fontsize=8, color=_AMBAR, fontname="helv")
        y += 14

    # Interpretación
    clase = interpretacion.get("clase")
    patron = interpretacion.get("patron")
    if clase or patron:
        y += 10
        page.draw_rect(fitz.Rect(M, y, 595 - M, y + (46 if (clase and patron) else 30)),
                       color=(0.9, 0.94, 0.98), fill=(0.96, 0.98, 1.0), width=0.5)
        y += 16
        if clase:
            page.insert_text((M + 8, y), f"Clase esquelética: {clase}", fontsize=9.5, color=_AZUL, fontname="helv")
            y += 15
        if patron:
            page.insert_text((M + 8, y), f"Patrón de crecimiento: {patron}", fontsize=9.5, color=_AZUL, fontname="helv")

    page.insert_text((M, 812), "Generado por MakingSmiles · medidas de referencia orientativas.",
                     fontsize=7.5, color=(0.6, 0.6, 0.6), fontname="helv")

    data = doc.tobytes()
    doc.close()
    return data
