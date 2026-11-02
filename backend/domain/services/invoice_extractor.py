"""Extractor de datos de factura recibida — lógica de dominio PURA (sin I/O).

Port del parser de SmileStudioPro .37: regex sobre asunto + cuerpo + texto del PDF,
parser de Facturae (XML) y normalización de proveedor. Determinista, sin secretos.
La capa de IA (LLM) se añade aparte en el servicio de aplicación.
"""
import re
import unicodedata
from datetime import date
from typing import Optional

PAT_TOTAL = [
    re.compile(r"(?:total|importe total|total a pagar|total con iva|total factura)[\s:]*([\d.,]+)\s*€?", re.I),
    re.compile(r"(?:total|importe)[\s:]*€?\s*([\d.,]+)", re.I),
    re.compile(r"(?:amount due|total due|grand total)[\s:]*€?\s*([\d.,]+)", re.I),
    re.compile(r"\btotal\b[^\d]*([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})", re.I),
]
PAT_BASE = [
    re.compile(r"(?:base imponible|base|subtotal|neto|importe sin iva|base iva)[\s:]*([\d.,]+)\s*€?", re.I),
    re.compile(r"(?:base|subtotal)[\s:]*€?\s*([\d.,]+)", re.I),
]
PAT_IVA = [
    re.compile(r"(?:iva|vat|tax)[\s:]*(\d{1,2})[\s%]*%", re.I),
    re.compile(r"(?:iva|vat)[\s:]*([\d]{1,2})[\s%]*", re.I),
    re.compile(r"(\d{1,2})\s*%\s*(?:iva|vat)", re.I),
]
PAT_NUMERO = [
    re.compile(r"(?:factura|invoice|n[º°o]\.?\s*factura|número|numero|ref\.?)[\s:#]*([A-Z0-9\-]{3,20})", re.I),
    re.compile(r"(?:factura|invoice)[\s:#]+([A-Z]{1,3}\d{2,8})", re.I),
    re.compile(r"\b(F\d{4,8}|INV-\d{4,8}|\d{4}-\d{4})\b", re.I),
]
PAT_FECHA = [
    re.compile(r"(\d{2}[/\-.]\d{2}[/\-.]\d{4})"),
    re.compile(r"(\d{2}[/\-.]\d{2}[/\-.]\d{2})"),
    re.compile(r"(\d{4}[/\-.]\d{2}[/\-.]\d{2})"),
]
PAT_CIF = re.compile(r"\b([A-Z]\d{8}|\d{8}[A-Z]|[A-Z]\d{7}[A-Z0-9])\b")

KEYWORDS_FACTURA = re.compile(
    r"factura|facturas|invoice|invoices|recibo|recibos|recib|abono|abonos|cargo|cargos|"
    r"pago|pagos|comprobante|comprobantes|nota de cargo|nota de abono", re.I)
NUMERO_BASURA = re.compile(
    r"^(disponible|factura|facturas|invoice|recibo|recibos|documento|pdf|aqui|aquí|ver|"
    r"descargar|nueva|online|web|email|correo|adjunto)$", re.I)
SOCIETARIO_RE = re.compile(
    r"\b(s\.?l\.?p?\.?|s\.?a\.?|s\.?l\.?l\.?|s\.?coop\.?|sociedad\s+limitada|"
    r"sociedad\s+anonima|llc|inc|ltd|pbc|gmbh|pte)\b", re.I)
# Anclas de "descargar factura" (texto del enlace, no la URL — como el escenario Make .37).
ANCLA_DESCARGA = re.compile(
    r"descarga(?:r)?\s+(?:tu\s+|mi\s+|la\s+|su\s+|aqu[ií]\s+)?(?:factura|recibo|pdf)|"
    r"(?:ver|descargar)\s+factura\b|descarga(?:r)?\s+aqu[ií]|download\s+(?:your\s+)?invoice|"
    r"view\s+invoice|get\s+(?:your\s+)?invoice|"
    # enlace cuyo texto es "Factura 02695", "Recibo nº 123", "Invoice 2024-1"…
    r"\b(?:factura|recibo|invoice|albar[aá]n)\b\s*(?:n[ºo°.]?\s*)?[\w/-]*\d|"
    # o un texto de acción cortito: "descargar", "ver", "aquí", "download", "view", "PDF"
    r"^\s*(?:descargar|descarga|ver|aqu[ií]|download|view|pdf)\s*$", re.I)


def to_number(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    c = raw.strip()
    if "," in c and "." in c:
        c = c.replace(".", "").replace(",", ".") if c.rfind(",") > c.rfind(".") else c.replace(",", "")
    elif "," in c:
        parts = c.split(",")
        c = c.replace(",", ".") if (len(parts) == 2 and len(parts[1]) <= 2) else c.replace(",", "")
    try:
        return float(c)
    except ValueError:
        return None


def to_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    m = re.match(r"^(\d{2})[/\-.](\d{2})[/\-.](\d{4})$", raw)
    if m:
        return _safe(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r"^(\d{2})[/\-.](\d{2})[/\-.](\d{2})$", raw)
    if m:
        yy = int(m.group(3))
        return _safe(2000 + yy if yy < 50 else 1900 + yy, int(m.group(2)), int(m.group(1)))
    m = re.match(r"^(\d{4})[/\-.](\d{2})[/\-.](\d{2})$", raw)
    if m:
        return _safe(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _safe(y: int, mo: int, d: int) -> Optional[date]:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _buscar(texto: str, pats: list[re.Pattern]) -> Optional[str]:
    for p in pats:
        m = p.search(texto)
        if m and m.group(1):
            return m.group(1)
    return None


def enlaces_factura(html: str) -> list[str]:
    """Enlaces de descarga de factura: anclas cuyo TEXTO indica descarga + URLs .pdf/.xml."""
    out, vistos = [], set()
    def add(u: str) -> None:
        v = u.replace("&amp;", "&").strip()
        if v and v not in vistos:
            vistos.add(v); out.append(v)
    for a in re.finditer(r"<a\b[^>]*\bhref\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, re.I | re.S):
        texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", a.group(2))).strip()
        if texto and ANCLA_DESCARGA.search(texto) and re.match(r"^https?:", a.group(1), re.I):
            add(a.group(1))
    for u in re.findall(r"https?://[^\s<>\"']+\.(?:pdf|xml)(?:[?#][^\s<>\"']*)?", html, re.I):
        add(u)
    return out


def normalize_proveedor(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = SOCIETARIO_RE.sub(" ", s.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


_STOP_PROV = {"sl", "slu", "sa", "sau", "sll", "slp", "scp", "cb", "sociedad", "limitada",
              "unipersonal", "espana", "espanola", "iberica", "de", "del", "la", "el", "los",
              "las", "y", "com", "www", "equipo", "laboratorio", "labo", "contabilidad",
              "info", "noreply", "no", "reply", "administracion", "facturacion", "facturas",
              "gmbh", "inc", "ltd", "limited", "bv", "llc", "europe", "spain", "group"}


# Letra de control del DNI/NIF (persona física) y del NIE: índice = número % 23.
_NIF_LETRAS = "TRWAGMYFPDXBNJZSQVHLCKE"
# Letra de control del CIF (empresa) cuando corresponde letra en vez de dígito
# (entidades cuya primera letra es K, L, M, o de la lista N/P/Q/R/S/W): índice = suma%10.
_CTRL_CIF = "JABCDEFGHI"


def _control_cif_ok(c: str) -> bool:
    """¿El dígito/letra de control de un CIF de empresa español (9 chars) cuadra?"""
    suma = 0
    for i, d in enumerate(c[1:8]):
        x = int(d)
        if i % 2 == 0:               # posiciones impares (1,3,5,7): x2 y sumar dígitos
            x *= 2
            x = x // 10 + x % 10
        suma += x
    num = (10 - suma % 10) % 10
    return c[8] == str(num) or c[8] == _CTRL_CIF[num]


def normalizar_cif(s: Optional[str]) -> Optional[str]:
    """Normaliza un identificador fiscal a su forma CANÓNICA y RECHAZA los inválidos: así el
    agente nunca inventa una identidad equivocada ni duplica la misma empresa por el prefijo ES.
      · Pela el prefijo intracomunitario español 'ES' → 'ESA08820953' == 'A08820953'.
      · Valida el dígito de CONTROL de CIF/NIF/NIE; si no cuadra (misread del OCR) → None → revisar.
      · VAT extranjero real (PT/DE/IE…): se conserva tal cual (no comprobable por checksum).
      · EIN de EE.UU. (proveedores no europeos, p.ej. SaaS facturado en dólares): formato
        2 dígitos-7 dígitos. Se detecta ANTES de quitar el guion (es parte del formato, no
        ruido) para no confundirlo con un CIF español de 9 dígitos sin letra. Se antepone
        'US' — mismo principio que el prefijo de país del VAT europeo — para que la
        identidad nunca choque con un CIF/NIF español."""
    if not s:
        return None
    ein = re.match(r"^\s*(\d{2})-(\d{7})\s*$", s)
    if ein:
        return f"US{ein.group(1)}{ein.group(2)}"
    c = re.sub(r"[\s\-./]", "", s).upper()
    if c.startswith("ES") and re.match(r"^[0-9XYZABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]$", c[2:]):
        c = c[2:]                                              # ES intracomunitario español
    if re.match(r"^\d{8}[A-Z]$", c):                           # NIF persona
        return c if _NIF_LETRAS[int(c[:8]) % 23] == c[8] else None
    if re.match(r"^[XYZ]\d{7}[A-Z]$", c):                      # NIE
        n = int(str("XYZ".index(c[0])) + c[1:8])
        return c if _NIF_LETRAS[n % 23] == c[8] else None
    if re.match(r"^[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]$", c):     # CIF empresa
        return c if _control_cif_ok(c) else None
    if re.match(r"^[A-Z]{2}[A-Z0-9]{2,12}$", c) and re.search(r"\d", c):  # VAT extranjero
        return c
    return None


def merge(base: dict, extra: Optional[dict]) -> dict:
    """Completa los huecos de `base` con `extra` (no pisa lo ya extraído)."""
    if not extra:
        return base
    for k, v in extra.items():
        if base.get(k) in (None, "", 0) and v not in (None, ""):
            base[k] = v
    return base
