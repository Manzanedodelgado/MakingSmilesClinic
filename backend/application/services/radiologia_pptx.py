"""Presentación del caso en PPTX (python-pptx).

Compone una presentación con: portada (paciente), una diapositiva por radiografía (imagen +
modalidad + hallazgos) y las diapositivas de cefalometría (imagen trazada + medidas vs norma).
Determinista; recibe los datos ya resueltos por el router.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

import io
from datetime import date
from typing import Optional

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

_AZUL = RGBColor(0x01, 0x3B, 0x82)
_TEAL = RGBColor(0x1C, 0xA0, 0xD1)
_GRIS = RGBColor(0x64, 0x74, 0x80)


def _titulo(slide, texto: str, sub: Optional[str] = None):
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(0.9))
    tf = tb.text_frame
    tf.text = texto
    tf.paragraphs[0].font.size = Pt(24); tf.paragraphs[0].font.bold = True; tf.paragraphs[0].font.color.rgb = _AZUL
    if sub:
        p = tf.add_paragraph(); p.text = sub; p.font.size = Pt(13); p.font.color.rgb = _TEAL


def informe_pptx(*, paciente: str, num_historia: str, radiografias: list[dict],
                 cefalometrias: list[dict]) -> bytes:
    """radiografias: [{titulo, imagen_bytes, hallazgos:[str]}].
    cefalometrias: [{titulo, imagen_bytes, mediciones:{code:{label,valor,unidad,norma,desviacion}}, interpretacion}]."""
    prs = Presentation()
    prs.slide_width = Inches(10); prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # Portada
    s = prs.slides.add_slide(blank)
    caja = s.shapes.add_textbox(Inches(0.8), Inches(2.6), Inches(8.4), Inches(2))
    tf = caja.text_frame
    tf.text = "Estudio radiológico"
    tf.paragraphs[0].font.size = Pt(34); tf.paragraphs[0].font.bold = True; tf.paragraphs[0].font.color.rgb = _AZUL
    for txt in [f"Paciente: {paciente}", f"Nº historia: {num_historia}", f"Fecha: {date.today().strftime('%d/%m/%Y')}"]:
        p = tf.add_paragraph(); p.text = txt; p.font.size = Pt(15); p.font.color.rgb = _GRIS

    # Radiografías
    for rx in radiografias:
        s = prs.slides.add_slide(blank)
        _titulo(s, rx["titulo"])
        if rx.get("imagen_bytes"):
            try:
                s.shapes.add_picture(io.BytesIO(rx["imagen_bytes"]), Inches(0.5), Inches(1.4), height=Inches(5.4))
            except Exception:  # raiz: imagen que no encaja -> se omite del slide
                logger.warning("pptx: imagen no entra en slide (%s)", rx.get("titulo"), exc_info=True)
        hall = rx.get("hallazgos") or []
        if hall:
            tb = s.shapes.add_textbox(Inches(6.3), Inches(1.4), Inches(3.3), Inches(5))
            tf = tb.text_frame; tf.word_wrap = True
            tf.text = "Hallazgos"
            tf.paragraphs[0].font.bold = True; tf.paragraphs[0].font.color.rgb = _AZUL; tf.paragraphs[0].font.size = Pt(14)
            for h in hall:
                p = tf.add_paragraph(); p.text = f"• {h}"; p.font.size = Pt(12); p.font.color.rgb = _GRIS

    # Cefalometrías
    for cef in cefalometrias:
        s = prs.slides.add_slide(blank)
        _titulo(s, cef["titulo"])
        if cef.get("imagen_bytes"):
            try:
                s.shapes.add_picture(io.BytesIO(cef["imagen_bytes"]), Inches(0.5), Inches(1.4), height=Inches(5.4))
            except Exception:  # raiz: imagen cefalométrica que no encaja -> se omite
                logger.warning("pptx: imagen cefalométrica no entra (%s)", cef.get("titulo"), exc_info=True)
        # tabla de medidas
        med = cef.get("mediciones") or {}
        rows = len(med) + 1
        if rows > 1:
            tabla = s.shapes.add_table(rows, 3, Inches(6.2), Inches(1.4), Inches(3.4), Inches(0.3 * rows)).table
            for j, h in enumerate(["Medida", "Valor", "Norma"]):
                c = tabla.cell(0, j); c.text = h
                c.text_frame.paragraphs[0].font.size = Pt(10); c.text_frame.paragraphs[0].font.bold = True
            for i, m in enumerate(med.values(), start=1):
                vals = [str(m.get("label", "")), f"{m.get('valor')}{m.get('unidad','')}",
                        (f"{m.get('norma')}" if m.get("norma") is not None else "")]
                for j, v in enumerate(vals):
                    c = tabla.cell(i, j); c.text = v; c.text_frame.paragraphs[0].font.size = Pt(9)
        interp = cef.get("interpretacion") or {}
        linea = " · ".join(x for x in [interp.get("clase"), interp.get("patron")] if x)
        if linea:
            tb = s.shapes.add_textbox(Inches(6.2), Inches(1.4) + Inches(0.32 * rows) + Inches(0.2), Inches(3.4), Inches(1.5))
            tf = tb.text_frame; tf.word_wrap = True; tf.text = linea
            tf.paragraphs[0].font.size = Pt(11); tf.paragraphs[0].font.color.rgb = _AZUL

    out = io.BytesIO(); prs.save(out)
    return out.getvalue()
