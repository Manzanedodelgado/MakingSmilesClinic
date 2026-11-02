"""Informe del estudio de ortodoncia en PDF (PyMuPDF) — la serie fotográfica del estudio en una
rejilla, con cabecera de paciente + etapa + fecha. Para imprimir o adjuntar (WhatsApp/email)."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

import io
from datetime import date
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

_AZUL = (0x01 / 255, 0x3b / 255, 0x82 / 255)
_TEAL = (0x1c / 255, 0xa0 / 255, 0xd1 / 255)
_GRIS = (0.45, 0.45, 0.45)

_NOMBRE = {
    "frontal_reposo": "Frontal reposo", "frontal_sonrisa": "Frontal sonrisa", "perfil_derecho": "Perfil derecho",
    "tres_cuartos_sonrisa": "Tres cuartos", "intraoral_frontal": "Intraoral frontal",
    "intraoral_lateral_derecha": "Lateral dcha.", "intraoral_lateral_izquierda": "Lateral izq.",
    "oclusal_superior": "Oclusal superior", "oclusal_inferior": "Oclusal inferior", "overjet_lateral": "Overjet",
}


def informe_estudio_pdf(*, paciente: str, num_historia: str, etapa: str, fecha: Optional[str],
                        fotos: list[dict], media_dir: Path) -> bytes:
    """fotos: [{tipo, archivo}] (archivo relativo a media_dir). Rejilla 3 columnas."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    M = 36

    page.insert_text((M, 50), "Estudio de ortodoncia", fontsize=18, color=_AZUL, fontname="hebo")
    page.insert_text((M, 70), f"Etapa: {etapa.capitalize()}", fontsize=11, color=_TEAL, fontname="helv")
    page.insert_text((M, 88), f"Paciente: {paciente}   ·   Nº historia: {num_historia}", fontsize=10, color=_GRIS, fontname="helv")
    fecha_txt = fecha or date.today().isoformat()
    page.insert_text((M, 102), f"Fecha del estudio: {fecha_txt}", fontsize=10, color=_GRIS, fontname="helv")
    page.draw_line(fitz.Point(M, 112), fitz.Point(595 - M, 112), color=_TEAL, width=1)

    # Rejilla 3 columnas
    cols, gap = 3, 10
    cw = (595 - 2 * M - (cols - 1) * gap) / cols
    ch = cw * 0.75  # 4:3
    x0, y0 = M, 126
    fila_alto = ch + 22
    por_pagina = 3 * 4  # 4 filas por página

    def nueva_pagina():
        p = doc.new_page(width=595, height=842)
        return p

    p = page
    for idx, f in enumerate(fotos):
        en_pagina = idx % por_pagina
        if idx > 0 and en_pagina == 0:
            p = nueva_pagina()
            y0 = 40
        fila = en_pagina // cols
        col = en_pagina % cols
        x = x0 + col * (cw + gap)
        y = y0 + fila * fila_alto
        rect = fitz.Rect(x, y, x + cw, y + ch)
        p.draw_rect(rect, color=(0.85, 0.85, 0.85), width=0.5)
        ruta = media_dir / f.get("archivo", "")
        if ruta.exists():
            try:
                p.insert_image(rect, filename=str(ruta), keep_proportion=True)
            except Exception:  # raiz: el PDF sale sin esa imagen antes que no salir
                pass
        etiqueta = _NOMBRE.get(f.get("tipo", ""), f.get("tipo", ""))
        p.insert_text((x + 2, y + ch + 12), etiqueta, fontsize=8, color=_AZUL, fontname="helv")

    doc[-1].insert_text((M, 812), "Generado por MakingSmiles.", fontsize=7.5, color=(0.6, 0.6, 0.6), fontname="helv")
    data = doc.tobytes()
    doc.close()
    return data
