"""VERI*FACTU — núcleo del registro de facturación: huella encadenada + QR de cotejo.

Capa de dominio PURA (sin BD, sin red): las reglas fiscales se implementan aquí una sola
vez y las usan todos los emisores de la app (facturas a pacientes, autofacturas, cualquier
factura futura). Quien necesite el hash NO lo recalcula por su cuenta.

Fuentes (verificadas contra el documento oficial, no de memoria):
  · AEAT, «Detalle de las especificaciones técnicas para generación de la huella o hash de
    los registros de facturación», v0.1.2 (27-08-2024) — art. 13 Orden HAC/1177/2024.
  · AEAT, «Detalle de las especificaciones técnicas del código QR de la factura» — arts. 20 y
    21 de la misma Orden.
  · RD 1007/2023; plazos vigentes tras el RD-ley 15/2025: sistemas adaptados antes del
    1-1-2027 (contribuyentes del Impuesto sobre Sociedades) y del 1-7-2027 (el resto).

Los tres ejemplos oficiales del documento de la huella están fijados como test en
`backend/tests/test_verifactu.py`: si alguien toca el orden de los campos, el separador o el
formato de fechas/importes, el hash deja de coincidir con el de la AEAT y el test lo caza.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union
from urllib.parse import quote

# ───────────────────────── QR (arts. 20-21 de la Orden) ─────────────────────────
# Servicio de cotejo. "ValidarQR" para sistemas que emiten facturas VERIFICABLES
# (VERI*FACTU, con remisión a la AEAT); "ValidarQRNoVerifactu" para los que no.
QR_PRODUCCION = "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/"
QR_PRUEBAS = "https://prewww2.aeat.es/wlpl/TIKE-CONT/"
# Textos obligatorios en la factura impresa (art. 20.1.b y detalle de presentación).
LEYENDA_QR = "QR tributario:"                                    # SIEMPRE, encima del QR
LEYENDA_VERIFACTU = "Factura verificable en la sede electrónica de la AEAT"   # solo VERI*FACTU
# Presentación: 30x30–40x40 mm, ISO/IEC 18004:2015, corrección de errores nivel M,
# ≥2 mm de zona en blanco (6 recomendados), arriba y antes del contenido de la factura.
QR_LADO_MM_MIN, QR_LADO_MM_MAX = 30, 40
QR_NIVEL_CORRECCION = "M"
QR_MARGEN_MM = 6

Importe = Union[Decimal, float, int, str]


def _txt(v: Optional[str]) -> str:
    """Valor tal cual va en el XML, sin espacios al inicio ni al final (espec. §3)."""
    return (v or "").strip()


def _imp(v: Optional[Importe]) -> str:
    """Importe con punto decimal y 2 decimales.

    La AEAT trata igual «123.1» y «123.10» (los ceros a la derecha no cuentan para la
    huella), así que fijamos 2 decimales: es lo que va en el XML y en el QR, y hace el
    resultado determinista.
    """
    if v is None or v == "":
        return ""
    return f"{Decimal(str(v)).quantize(Decimal('0.01'))}"


def _fecha(f: Optional[Union[date, str]]) -> str:
    """Fecha de expedición en DD-MM-AAAA (formato del XML y del parámetro `fecha` del QR)."""
    if not f:
        return ""
    if isinstance(f, str):
        return f.strip()
    return f.strftime("%d-%m-%Y")


def _cadena(campos: list[tuple[str, str]]) -> str:
    """`nombre1=valor1&nombre2=valor2&…` en el orden dado (espec. §3).
    Un campo ausente o vacío va igual, con el «=» y sin valor."""
    return "&".join(f"{n}={v}" for n, v in campos)


def _sha256(cadena: str) -> str:
    """SHA-256 de la cadena en UTF-8 → hexadecimal en MAYÚSCULAS, 64 caracteres (§2 y §5)."""
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


# ───────────────────────── registro de ALTA ─────────────────────────
def cadena_alta(*, id_emisor: str, num_serie: str, fecha_expedicion: Union[date, str],
                tipo_factura: str, cuota_total: Optional[Importe],
                importe_total: Optional[Importe], huella_anterior: Optional[str],
                fecha_hora_huso: str) -> str:
    """Cadena de entrada de la huella de un registro de ALTA, en el orden EXACTO de la
    espec. §3.a. `huella_anterior` vacía = primer registro del sistema (PrimerRegistro='S')."""
    return _cadena([
        ("IDEmisorFactura", _txt(id_emisor)),
        ("NumSerieFactura", _txt(num_serie)),
        ("FechaExpedicionFactura", _fecha(fecha_expedicion)),
        ("TipoFactura", _txt(tipo_factura)),          # catálogo: Lista L2 del anexo de la Orden
        ("CuotaTotal", _imp(cuota_total)),
        ("ImporteTotal", _imp(importe_total)),
        ("Huella", _txt(huella_anterior)),
        ("FechaHoraHusoGenRegistro", _txt(fecha_hora_huso)),
    ])


def cadena_anulacion(*, id_emisor: str, num_serie: str,
                     fecha_expedicion: Union[date, str], huella_anterior: Optional[str],
                     fecha_hora_huso: str) -> str:
    """Cadena de entrada de la huella de un registro de ANULACIÓN (espec. §3.b).
    Ojo: los nombres de campo llevan el sufijo «Anulada» y NO son los del alta."""
    return _cadena([
        ("IDEmisorFacturaAnulada", _txt(id_emisor)),
        ("NumSerieFacturaAnulada", _txt(num_serie)),
        ("FechaExpedicionFacturaAnulada", _fecha(fecha_expedicion)),
        ("Huella", _txt(huella_anterior)),
        ("FechaHoraHusoGenRegistro", _txt(fecha_hora_huso)),
    ])


def huella_alta(**kwargs) -> str:
    """SHA-256 (hex, mayúsculas) de `cadena_alta(**kwargs)` — el valor que va en el
    campo `Huella` del registro y el que encadena el siguiente registro."""
    return _sha256(cadena_alta(**kwargs))


def huella_anulacion(**kwargs) -> str:
    """SHA-256 (hex, mayúsculas) de `cadena_anulacion(**kwargs)`."""
    return _sha256(cadena_anulacion(**kwargs))


def marca_temporal(dt: datetime) -> str:
    """`FechaHoraHusoGenRegistro`: ISO 8601 con huso, SIN microsegundos (espec. §3)."""
    return dt.replace(microsecond=0).isoformat()


def url_qr(*, nif: str, num_serie: str, fecha_expedicion: Union[date, str],
           importe_total: Importe, verificable: bool = True, pruebas: bool = False) -> str:
    """URL del código QR de cotejo (arts. 20-21 de la Orden). `verificable=False` (sistemas
    NO VERI*FACTU) usa el endpoint ValidarQRNoVerifactu en vez de ValidarQR."""
    base = QR_PRUEBAS if pruebas else QR_PRODUCCION
    endpoint = "ValidarQR" if verificable else "ValidarQRNoVerifactu"
    params = [
        ("nif", nif),
        ("numserie", num_serie),
        ("fecha", _fecha(fecha_expedicion)),
        ("importe", _imp(importe_total)),
    ]
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params)
    return f"{base}{endpoint}?{query}"

