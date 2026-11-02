"""Generación del PDF de receta médica privada (formato oficial español).

No existe una plantilla en blanco que rellenar (a diferencia de los consentimientos
COEM): el documento se DIBUJA desde cero con PyMuPDF, replicando el layout de una
receta médica privada real (dos paneles en una página A4: "RECETA MÉDICA PRIVADA"
para la farmacia arriba, "INFORMACIÓN AL PACIENTE" abajo — coordenadas tomadas de un
ejemplo real de referencia).

El código de barras NO se calcula aquí: es el `cve` que ya viene con cada número del
talonario oficial subido por el doctor (columna 2 del CSV/XML importado) — solo se
renderiza como imagen Code128.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Optional

import fitz  # PyMuPDF

_NEGRO = (0, 0, 0)
_A4 = (595, 842)


def _barcode_png(codigo: str) -> Optional[bytes]:
    """Code128 del `cve` del talonario. None si no hay cve o falla la generación
    (nunca debe romper la emisión de la receta por esto)."""
    if not codigo:
        return None
    try:
        import barcode
        from barcode.writer import ImageWriter
        buf = io.BytesIO()
        barcode.Code128(codigo, writer=ImageWriter()).write(
            buf, options={"write_text": False, "module_height": 10, "quiet_zone": 1})
        return buf.getvalue()
    except Exception:  # raiz: el numero en texto ya es suficiente; el PDF no se bloquea
        return None


def _fecha_larga(d: Optional[date]) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _panel(page: "fitz.Page", y0: float, *, numero_receta: str, cve: Optional[str],
           paciente_nombre: str, paciente_fecha_nac: str, paciente_nif: str,
           prescriptor_nombre: str, num_colegiado: str, centro_direccion: str,
           centro_poblacion: str, fecha_prescripcion: str,
           medicamento: str, envases_unidades: str, duracion: str,
           posologia_forma: str, unidades: str, pauta: str,
           orden_dispensacion: str, fecha_prevista: str,
           es_farmacia: bool, diagnostico: str = "", instrucciones: str = "",
           urgencia: bool = False, desabastecimiento: bool = False,
           motivo_sustitucion: str = "") -> None:
    """Dibuja UN panel (farmacia o paciente) — mismo layout, cambia el bloque inferior."""
    f8, f9, f10 = 8, 9, 10.5

    def put(x, y, txt, size=f9, bold=False):
        if txt:
            page.insert_text((x, y0 + y), str(txt), fontsize=size, color=_NEGRO,
                             fontname="helv" if not bold else "hebo")

    # Marco general y cabecera
    page.draw_rect(fitz.Rect(30, y0 + 10, 565, y0 + 400), color=_NEGRO, width=0.8)
    page.draw_rect(fitz.Rect(30, y0 + 10, 130, y0 + 30), color=_NEGRO, width=0.8)
    put(35, 24, f"Nº Receta: {numero_receta}", size=f10, bold=True)
    put(220, 45, "RECETA MÉDICA", size=13, bold=True)
    put(175, 60, "ASISTENCIA SANITARIA PRIVADA" if es_farmacia else
        "INFORMACIÓN AL PACIENTE - ASISTENCIA PRIVADA", size=10.5, bold=True)

    # Columna izquierda: prescripción
    put(35, 92, "PRESCRIPCIÓN — medicamento, forma farmacéutica,", size=f8)
    put(35, 101, "vía de administración, dosis y unidades por envase", size=f8)
    put(35, 148, f"Nº envases/unidades: {envases_unidades}", size=f9)
    put(35, 168, medicamento, size=f10, bold=True)

    # Columna central: duración / posología / dispensación
    put(275, 90, "Duración del tratamiento", size=f8)
    put(295, 100, duracion, size=f9)
    put(295, 112, "Posología", size=f8)
    put(285, 122, posologia_forma, size=f9)
    put(255, 135, "Unidades", size=f8);  put(320, 135, "Pauta", size=f8)
    put(258, 146, unidades, size=f9);    put(300, 146, pauta, size=f9)
    put(275, 159, "Nº. Orden dispensación", size=f8)
    put(305, 169, orden_dispensacion, size=f9)
    put(265, 182, "Fecha prevista dispensación", size=f8)
    put(295, 192, fecha_prevista, size=f9)

    # Columna derecha: paciente + prescriptor
    put(383, 93, "PACIENTE (nombre, apellidos, fecha nacimiento, NIF/NIE)", size=f8)
    put(383, 116, paciente_nombre, size=f9, bold=True)
    put(383, 128, f"{paciente_fecha_nac}   ·   {paciente_nif}", size=f9)
    put(383, 158, "PRESCRIPTOR (nombre, nº colegiado, dirección)", size=f8)
    put(383, 181, prescriptor_nombre, size=f9, bold=True)
    put(383, 193, f"Nº Colegiado {num_colegiado}", size=f9)
    put(383, 205, centro_direccion, size=f9)
    put(383, 217, centro_poblacion, size=f9)
    put(383, 241, "Fecha de la prescripción*", size=f8)
    put(383, 250, fecha_prescripcion, size=f9)

    # Bloque inferior: distinto según panel
    page.draw_line(fitz.Point(30, y0 + 268), fitz.Point(565, y0 + 268), color=_NEGRO, width=0.6)
    if es_farmacia:
        put(35, 278, "Información al farmacéutico, en su caso:", size=f8)
        put(45, 293, ("☒" if urgencia else "☐") + " Urgencia", size=f9)
        put(45, 306, ("☒" if desabastecimiento else "☐") + " Desabastecimiento", size=f9)
        put(270, 278, "Motivo de la sustitución / FARMACIA:", size=f8)
        put(270, 293, motivo_sustitucion, size=f9)
        put(275, 206, "Firma de Farmacéutico", size=f8)
    else:
        put(35, 278, "Diagnóstico/s (si procede):", size=f8)
        put(35, 291, diagnostico, size=f9)
        put(35, 313, "Instrucciones al paciente (si procede):", size=f8)
        put(35, 326, instrucciones, size=f9)

    # Nota legal + código de barras
    put(35, 342,
        "*La validez de esta receta expira a los 10 días naturales de la fecha prevista de", size=6.5)
    put(35, 350,
        "dispensación (o de prescripción). Tratamiento no superior a 3 meses. Receta válida", size=6.5)
    put(35, 358,
        "para una única dispensación, en cualquier oficina de farmacia del territorio nacional.", size=6.5)

    png = _barcode_png(cve or numero_receta)
    if png:
        page.insert_image(fitz.Rect(230, y0 + 335, 400, y0 + 375), stream=png)
    else:
        put(260, 358, cve or numero_receta, size=8)


def generar_receta_pdf(*, numero_receta: str, cve: Optional[str],
                       paciente_nombre: str, paciente_fecha_nac: str, paciente_nif: str,
                       prescriptor_nombre: str, num_colegiado: str,
                       centro_direccion: str, centro_poblacion: str,
                       fecha_prescripcion: date, diagnostico: str,
                       instrucciones: str, urgencia: bool, desabastecimiento: bool,
                       motivo_sustitucion: str,
                       lineas: list[dict]) -> bytes:
    """Genera el PDF completo de una receta (1 página por cada línea de medicamento,
    cada una con sus 2 paneles). `lineas` = [{medicamento, envases, duracion, forma,
    unidades, pauta, orden, fecha_prevista}, ...] ya resueltas por el llamante."""
    doc = fitz.open()
    fecha_txt = _fecha_larga(fecha_prescripcion)
    for ln in (lineas or [{}]):
        page = doc.new_page(width=_A4[0], height=_A4[1])
        kwargs = dict(
            numero_receta=numero_receta, cve=cve,
            paciente_nombre=paciente_nombre, paciente_fecha_nac=paciente_fecha_nac,
            paciente_nif=paciente_nif, prescriptor_nombre=prescriptor_nombre,
            num_colegiado=num_colegiado, centro_direccion=centro_direccion,
            centro_poblacion=centro_poblacion, fecha_prescripcion=fecha_txt,
            medicamento=str(ln.get("medicamento") or ""),
            envases_unidades=str(ln.get("envases") or "1"),
            duracion=str(ln.get("duracion") or ""),
            posologia_forma=str(ln.get("forma") or ""),
            unidades=str(ln.get("unidades") or "1"),
            pauta=str(ln.get("pauta") or ""),
            orden_dispensacion=str(ln.get("orden") or "1"),
            fecha_prevista=str(ln.get("fecha_prevista") or fecha_txt),
            diagnostico=diagnostico or "", instrucciones=instrucciones or "",
            urgencia=urgencia, desabastecimiento=desabastecimiento,
            motivo_sustitucion=motivo_sustitucion or "",
        )
        _panel(page, 0, es_farmacia=True, **kwargs)
        _panel(page, 420, es_farmacia=False, **kwargs)
    out = doc.tobytes()
    doc.close()
    return out
