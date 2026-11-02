"""HTML→PDF en servidor usando LA MISMA plantilla que tiene configurada el centro.

Por qué existe: el cliente nuevo (`documentoDoc.ts`) pide el PDF al backend en vez de
generarlo en el navegador. Si el servidor pintara un PDF propio (ReportLab), el centro
perdería su plantilla, su firma y su sello — que es justo lo que NO se quiere perder.

Así que aquí se hace lo mismo que hacía el navegador:
  1. Se coge la plantilla HTML de `configuraciones · documentos.plantillas` (BD).
  2. Se sustituyen las variables `{{clave}}` en dos pasadas (igual que `renderDoc`
     en documentTemplates.ts), escapando todo salvo las claves que SON html.
  3. Se renderiza a PDF con PyMuPDF (fitz.Story).

Limitación conocida y aceptada: fitz.Story soporta un subconjunto de CSS (no grid ni
flex avanzados). El documento sale con el contenido y la estructura correctos; si una
plantilla usa CSS muy moderno puede perder algo de maquetación fina respecto al render
del navegador. El flujo de cliente (docBase.htmlToPdfBase64) sigue intacto para quien
necesite el render pixel-perfect.
"""
import html as _html
import re
from pathlib import Path

import fitz

# Claves cuyo valor ES html (no se escapan) — misma lista que DOC_HTML_KEYS en el front.
DOC_HTML_KEYS = {"clinicLogo", "sello", "clinicWeb", "odontograma", "lineas",
                 "registros", "barcode", "firma"}

_VAR = re.compile(r"\{\{(\w+)\}\}")


def render_plantilla(html_plantilla: str, campos: dict, datos: dict) -> str:
    """Sustituye {{variables}} en dos pasadas, como hace `renderDoc` en el front
    (una variable puede expandirse a otro fragmento que a su vez tenga variables)."""
    variables = {**(datos or {}), **(campos or {})}

    def _sub(texto: str) -> str:
        def _uno(m):
            k = m.group(1)
            v = variables.get(k, (datos or {}).get(k, ""))
            v = "" if v is None else str(v)
            return v if k in DOC_HTML_KEYS else _html.escape(v, quote=True)
        return _VAR.sub(_uno, texto)

    return _sub(_sub(html_plantilla))


def html_a_pdf(html_documento: str, pdf_path: Path, css: str = "") -> None:
    """Renderiza el HTML del documento a PDF (A4) con fitz.Story."""
    story = fitz.Story(html=html_documento, user_css=css or None)
    writer = fitz.DocumentWriter(str(pdf_path))
    # A4 en puntos, con márgenes de 36pt (0,5")
    medio = fitz.paper_rect("a4")
    area = medio + (36, 36, -36, -36)
    mas = True
    while mas:
        dispositivo = writer.begin_page(medio)
        mas, _ = story.place(area)
        story.draw(dispositivo)
        writer.end_page()
    writer.close()
