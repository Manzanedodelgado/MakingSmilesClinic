"""PDF Report — generador de reportes clínicos ortodóncicos."""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors

from domain.models.ortodoncia import CasoOrtodoncia


# Colores MakingSmiles
NAVY = HexColor("#013b82")
CYAN = HexColor("#1ca0d1")
BRAND = HexColor("#1500A0")
ACCENT = HexColor("#2DD9C3")


async def generar_pdf_caso(caso: CasoOrtodoncia) -> str:
    """Genera PDF con mediciones, diagnóstico y plan del caso."""

    # Crear directorio temporal para PDFs
    pdf_dir = Path("/tmp/makingsmiles_pdfs")
    pdf_dir.mkdir(exist_ok=True)

    # Ruta del PDF
    pdf_path = pdf_dir / f"caso_{caso.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    # Crear documento
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    # Estilos
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=NAVY,
        spaceAfter=12,
        alignment=1,  # Center
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=BRAND,
        spaceAfter=10,
        spaceBefore=10,
    )
    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
    )

    # Contenido
    story = []

    # Título
    story.append(Paragraph("REPORTE ORTODÓNTICO", title_style))
    story.append(Spacer(1, 0.3 * inch))

    # Información del caso
    story.append(Paragraph("Información del Caso", heading_style))
    info_data = [
        ["ID Caso:", str(caso.id)],
        ["Paciente ID:", str(caso.paciente_id)],
        ["Centro ID:", str(caso.centro_id)],
        ["Fecha Creación:", caso.fecha_creacion.strftime("%d/%m/%Y") if caso.fecha_creacion else "N/A"],
    ]
    info_table = Table(info_data, colWidths=[2 * inch, 4 * inch])
    info_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), CYAN),
            ("TEXTCOLOR", (0, 0), (0, -1), "white"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ])
    )
    story.append(info_table)
    story.append(Spacer(1, 0.2 * inch))

    # Mediciones
    if caso.mediciones_json:
        story.append(Paragraph("Mediciones Cefalométricas", heading_style))
        try:
            mediciones = json.loads(caso.mediciones_json) if isinstance(caso.mediciones_json, str) else caso.mediciones_json
            if mediciones:
                med_data = [["Parámetro", "Valor"]]
                for param, valor in mediciones.items():
                    med_data.append([param, f"{valor}°" if isinstance(valor, (int, float)) else str(valor)])

                med_table = Table(med_data, colWidths=[3 * inch, 2 * inch])
                med_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                        ("TEXTCOLOR", (0, 0), (-1, 0), "black"),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor("#f0f0f0")]),
                    ])
                )
                story.append(med_table)
                story.append(Spacer(1, 0.2 * inch))
        except Exception as e:  # raiz: mediciones malformadas -> nota en el PDF, no aborta
            story.append(Paragraph(f"<i>Error al procesar mediciones: {str(e)}</i>", normal_style))
            story.append(Spacer(1, 0.1 * inch))

    # Diagnóstico
    if caso.diagnostico_texto:
        story.append(Paragraph("Diagnóstico Clínico", heading_style))
        story.append(Paragraph(caso.diagnostico_texto, normal_style))
        story.append(Spacer(1, 0.1 * inch))

        # Clasificación
        clasificacion_data = []
        if caso.diagnostico_clase:
            clasificacion_data.append(["Clase Molar:", f"Clase {caso.diagnostico_clase}"])
        if caso.diagnostico_patron:
            clasificacion_data.append(["Patrón Vertical:", caso.diagnostico_patron.capitalize()])

        if clasificacion_data:
            clasificacion_table = Table(clasificacion_data, colWidths=[2 * inch, 4 * inch])
            clasificacion_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (0, -1), BRAND),
                    ("TEXTCOLOR", (0, 0), (0, -1), "white"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                ])
            )
            story.append(clasificacion_table)
            story.append(Spacer(1, 0.2 * inch))

    # Plan de Tratamiento
    if caso.plan_tratamiento_json:
        story.append(Paragraph("Plan de Tratamiento", heading_style))
        try:
            plan = json.loads(caso.plan_tratamiento_json) if isinstance(caso.plan_tratamiento_json, str) else caso.plan_tratamiento_json
            if plan:
                plan_text = plan.get("descripcion", str(plan))
                story.append(Paragraph(plan_text, normal_style))
                story.append(Spacer(1, 0.2 * inch))
        except Exception as e:  # raiz: plan malformado -> nota en el PDF, no aborta
            story.append(Paragraph(f"<i>Error al procesar plan: {str(e)}</i>", normal_style))
            story.append(Spacer(1, 0.1 * inch))

    # Pie de página
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(
        f"<i>Reporte generado el {datetime.now().strftime('%d/%m/%Y a las %H:%M')}</i>",
        normal_style
    ))

    # Construir PDF
    doc.build(story)

    return str(pdf_path)
