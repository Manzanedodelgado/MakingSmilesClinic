"""Validación de los datos de una factura — lógica de dominio PURA (sin I/O ni BD).

Lo usa el AGENTE de facturas (como herramientas que puede invocar) y el re-proceso.
Detecta lo que el pipeline antiguo ignoraba: fechas imposibles, importes incoherentes,
y CIF que en realidad es el del receptor (auto-factura mal leída).
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from domain.services.invoice_extractor import normalizar_cif

TIPOS_IVA = [Decimal("0"), Decimal("4"), Decimal("10"), Decimal("21")]


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def validar_fecha(fecha: Optional[date], hoy: date) -> dict:
    """Rango razonable de una factura: 2015 .. año siguiente. Fuera → imposible."""
    if not fecha:
        return {"valida": False, "motivo": "sin_fecha"}
    if fecha.year < 2015 or fecha.year > hoy.year + 1:
        return {"valida": False, "motivo": "fecha_imposible"}
    return {"valida": True, "motivo": None}


def validar_importes(base, iva_pct, total, suplido=0, retencion=0) -> dict:
    """Coherencia base/IVA/total contemplando SUPLIDO y RETENCIÓN:

        total = base + round(base*iva_pct/100) − retención + suplido

    El suplido (gasto exento que el proveedor adelanta por cuenta del cliente) y la retención
    de IRPF NO son IVA: se descuentan ANTES de medir el tipo. El IVA implícito debe encajar en
    un tipo legal (0/4/10/21) o, como mucho, el máximo de la UE (~27%). Si se detecta un residual
    exento que cuadra como suplido pero no está registrado, se marca 'suplido_no_registrado'
    (no se inventa el dato: solo se señala para que el re-proceso lo rellene).

    Devuelve {coherente, iva_calculado, incidencias, suplido_sugerido}. MANTIENE el retorno dict
    del validador original: lo consumen `validar()`, la contabilización y el re-proceso.
    """
    base, total, iva = _dec(base), _dec(total), _dec(iva_pct)
    sup, ret = _dec(suplido), _dec(retencion)
    inc: list[str] = []
    if total == 0:
        inc.append("total_cero")
    elif total < 0:                      # abono/rectificativa: importes negativos legítimos
        base, total, sup = abs(base), abs(total), abs(sup)   # se validan por su valor absoluto
    # Importe que debería ser SOLO base + IVA (quitando lo exento: suplido y retención de IRPF).
    neto_iva = total - sup + ret
    if total > 0 and base > neto_iva + Decimal("0.02"):
        inc.append("base_mayor_total")
    iva_calc = None
    if base > 0 and total > 0:
        ratio = (neto_iva - base) / base * 100
        # Una factura puede MEZCLAR tipos (21% + 0% exento) y los proveedores EXTRANJEROS aplican
        # su IVA (Portugal 23%, Hungría 27%…). El tipo EFECTIVO legítimo va de 0 al máximo de la UE
        # (~27%). Solo es incoherente si se sale de ahí (p.ej. base mal leída → 38%).
        if ratio < Decimal("-1") or ratio > Decimal("28"):
            inc.append("iva_incoherente")
        else:
            iva_calc = min(TIPOS_IVA, key=lambda t: abs(t - ratio))  # tipo más cercano (orientativo)
    if iva and (iva < 0 or iva > 28):     # 28 = máximo de la UE (Hungría 27%); no solo el 21 español
        inc.append("iva_fuera_rango")
    # Detección de SUPLIDO no registrado: residual exento tras cuadrar base + IVA − retención.
    # Guard (0.01, base*2): por encima de 2× la base ya no es un suplido sino la factura mal leída
    # (p.ej. base=0 → cualquier total caería aquí; se excluye y va a revisión manual).
    suplido_sugerido = None
    if sup == 0 and base > 0 and total > 0:
        cuota = (base * iva / 100).quantize(Decimal("0.01"))
        residual = (total - base - cuota + ret).quantize(Decimal("0.01"))
        if Decimal("0.01") < residual < base * 2:
            inc.append("suplido_no_registrado")
            suplido_sugerido = float(residual)
    return {"coherente": not inc,
            "iva_calculado": float(iva_calc) if iva_calc is not None else None,
            "incidencias": inc,
            "suplido_sugerido": suplido_sugerido}


def validar_cif(cif: Optional[str], cifs_receptor: Optional[list]) -> dict:
    """Normaliza el CIF y comprueba que NO sea el de la propia clínica (receptor)."""
    n = normalizar_cif(cif)
    if not n:
        return {"normalizado": None, "valido": False, "es_receptor": False}
    rec = {normalizar_cif(c) for c in (cifs_receptor or []) if c}
    return {"normalizado": n, "valido": True, "es_receptor": n in rec}


def validar(datos: dict, hoy: date, cifs_receptor: Optional[list] = None) -> tuple[dict, list]:
    """Sanea los datos extraídos y devuelve (datos_saneados, lista_incidencias).
    Punto único de validación reutilizado por el agente y por el re-proceso."""
    d = dict(datos or {})
    inc: list[str] = []

    vc = validar_cif(d.get("cif"), cifs_receptor)
    if vc["es_receptor"]:
        inc.append("cif_receptor")
        d["cif"] = None
        d["proveedor"] = None          # si el CIF es el de la clínica, el "emisor" leído es falso
    else:
        d["cif"] = vc["normalizado"]   # None si no era un CIF válido

    f = d.get("fecha_factura")
    vf = validar_fecha(f if isinstance(f, date) else None, hoy)
    if not vf["valida"] and f is not None:
        inc.append(vf["motivo"])

    vi = validar_importes(d.get("base_imponible"), d.get("iva_pct"), d.get("total"),
                          suplido=d.get("suplido"), retencion=d.get("retencion"))
    inc.extend(vi["incidencias"])
    if vi.get("suplido_sugerido") is not None and not d.get("suplido"):
        d["suplido_sugerido"] = vi["suplido_sugerido"]   # lo aprovecha el re-proceso (no se inventa)
    # NO se toca el IVA: se guarda el que pone la factura (incl. tipos extranjeros 19/20/23/27%).
    # El validador solo COMPRUEBA la coherencia base/total; no inventa ni snapping a tipo español.

    return d, inc
