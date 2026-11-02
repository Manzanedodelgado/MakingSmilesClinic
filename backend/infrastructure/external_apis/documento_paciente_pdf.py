"""PDF de factura / justificante de asistencia para la app del paciente.

Genera bytes de PDF en servidor (ReportLab) — necesario porque las apps nativas no
pueden usar el render HTML→PDF del navegador que usa la web. Mismo patrón visual que
`pdf_generator.py` (informe de ortodoncia): paleta corporativa, tablas ReportLab.

Decisión v1 (no un port del sistema de plantillas HTML editables de Config›Documentos):
más simple de verificar de extremo a extremo, con la marca correcta. No es pixel-perfect
con el PDF que genera el navegador — aceptable para v1 (YAGNI); portar el sistema de
plantillas a un renderer de servidor es un cambio más grande, para cuando haga falta
personalización real por parte del centro.
"""
from datetime import date, datetime
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

NAVY = HexColor("#013b82")
CYAN = HexColor("#1ca0d1")
BRAND = HexColor("#1500A0")
ACCENT = HexColor("#2DD9C3")

_STYLES = getSampleStyleSheet()
_TITLE = ParagraphStyle("PacienteTitle", parent=_STYLES["Heading1"], fontSize=22, textColor=NAVY,
                        spaceAfter=10, alignment=1)
_HEADING = ParagraphStyle("PacienteHeading", parent=_STYLES["Heading2"], fontSize=13, textColor=BRAND,
                          spaceAfter=8, spaceBefore=8)
_NORMAL = ParagraphStyle("PacienteNormal", parent=_STYLES["Normal"], fontSize=11, leading=15)


def _doc(pdf_path: Path) -> SimpleDocTemplate:
    return SimpleDocTemplate(str(pdf_path), pagesize=letter, rightMargin=0.75 * inch,
                             leftMargin=0.75 * inch, topMargin=0.75 * inch, bottomMargin=0.75 * inch)


def _centro_header(centro: dict) -> list:
    story = [Paragraph(centro.get("nombre") or "Clínica", _TITLE)]
    linea = " · ".join(x for x in [centro.get("direccion"), centro.get("poblacion"), centro.get("cif")] if x)
    if linea:
        story.append(Paragraph(linea, ParagraphStyle("sub", parent=_NORMAL, alignment=1, fontSize=9,
                                                      textColor=colors.grey)))
    story.append(Spacer(1, 0.3 * inch))
    return story


def render_factura_pdf(pdf_path: Path, *, centro: dict, paciente: dict, numero: str,
                        lineas: list[dict], total: float) -> None:
    doc = _doc(pdf_path)
    story = _centro_header(centro)
    story.append(Paragraph("FACTURA", _HEADING))
    info = Table([
        ["Nº factura:", numero],
        ["Fecha:", date.today().strftime("%d/%m/%Y")],
        ["Paciente:", paciente.get("nombre") or "—"],
        ["NIF:", paciente.get("nif") or "—"],
    ], colWidths=[1.7 * inch, 4.3 * inch])
    info.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info)
    story.append(Spacer(1, 0.2 * inch))

    filas = [["Fecha", "Concepto", "Doctor", "Importe"]]
    for l in lineas:
        filas.append([l.get("fecha") or "—", l.get("concepto") or "—", l.get("doctor") or "—",
                      f"{l.get('neto', 0):.2f} €"])
    filas.append(["", "", "TOTAL", f"{total:.2f} €"])
    tabla = Table(filas, colWidths=[1 * inch, 2.7 * inch, 1.6 * inch, 1 * inch])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, HexColor("#f4f6fb")]),
    ]))
    story.append(tabla)
    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph(
        "Tratamientos odontológicos — Exento de IVA (art. 20.Uno.3º Ley 37/1992).",
        ParagraphStyle("nota", parent=_NORMAL, fontSize=8, textColor=colors.grey),
    ))
    doc.build(story)


def render_justificante_pdf(pdf_path: Path, *, centro: dict, paciente: dict,
                            fecha: date, concepto: str, doctor: str) -> None:
    doc = _doc(pdf_path)
    story = _centro_header(centro)
    story.append(Paragraph("JUSTIFICANTE DE ASISTENCIA", _HEADING))
    texto = (
        f"Se certifica que <b>{paciente.get('nombre') or '—'}</b>"
        + (f" (NIF {paciente['nif']})" if paciente.get("nif") else "")
        + f" acudió a consulta en {centro.get('nombre') or 'esta clínica'} "
        f"el día <b>{fecha.strftime('%d/%m/%Y')}</b>"
        + (f" para: {concepto}." if concepto else ".")
        + (f" Atendido por {doctor}." if doctor and doctor != "—" else "")
    )
    story.append(Paragraph(texto, _NORMAL))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(
        f"Documento generado el {datetime.now().strftime('%d/%m/%Y a las %H:%M')}.",
        ParagraphStyle("nota", parent=_NORMAL, fontSize=8, textColor=colors.grey),
    ))
    doc.build(story)


def render_presupuesto_pdf(pdf_path: Path, *, centro: dict, paciente: dict, numero: str,
                           fecha: date, profesional: str, lineas: list[dict],
                           bruto: float, descuento: float, total: float,
                           notas: str | None = None) -> None:
    """PDF de presupuesto (mismo patrón visual que factura/justificante).

    `lineas` = [{concepto, pieza, cantidad, precio, descuento, neto}]. Los importes vienen
    ya calculados por el router (misma fuente que el endpoint /documento), este módulo
    solo pinta.
    """
    doc = _doc(pdf_path)
    story = _centro_header(centro)
    story.append(Paragraph("PRESUPUESTO", _HEADING))
    info = Table([
        ["Nº presupuesto:", numero],
        ["Fecha:", fecha.strftime("%d/%m/%Y") if fecha else date.today().strftime("%d/%m/%Y")],
        ["Paciente:", paciente.get("nombre") or "—"],
        ["NIF:", paciente.get("nif") or "—"],
        ["Profesional:", profesional or "—"],
    ], colWidths=[1.7 * inch, 4.3 * inch])
    info.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info)
    story.append(Spacer(1, 0.2 * inch))

    filas = [["Tratamiento", "Pieza/Zona", "Uds.", "Precio", "Dto.", "Importe"]]
    for l in lineas:
        filas.append([
            l.get("concepto") or "—", l.get("pieza") or "—", str(l.get("cantidad") or 1),
            f"{float(l.get('precio') or 0):.2f} €",
            f"{float(l.get('descuento') or 0):.2f} €" if l.get("descuento") else "—",
            f"{float(l.get('neto') or 0):.2f} €",
        ])
    if descuento:
        filas.append(["", "", "", "", "Bruto", f"{bruto:.2f} €"])
        filas.append(["", "", "", "", "Descuento", f"-{descuento:.2f} €"])
    filas.append(["", "", "", "", "TOTAL", f"{total:.2f} €"])
    tabla = Table(filas, colWidths=[2.3 * inch, 1.1 * inch, 0.5 * inch, 0.9 * inch, 0.8 * inch, 0.9 * inch])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (4, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, HexColor("#f4f6fb")]),
    ]))
    story.append(tabla)
    if notas:
        story.append(Spacer(1, 0.25 * inch))
        story.append(Paragraph(f"<b>Notas:</b> {notas}", _NORMAL))
    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph(
        "Presupuesto sin compromiso. Validez de 3 meses desde la fecha de emisión. "
        "Tratamientos odontológicos — Exento de IVA (art. 20.Uno.3º Ley 37/1992).",
        ParagraphStyle("nota", parent=_NORMAL, fontSize=8, textColor=colors.grey),
    ))
    doc.build(story)
