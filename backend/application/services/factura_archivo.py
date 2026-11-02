"""Archivado del PDF de la factura de un gasto.

Los DATOS de la factura viven en la web (BD → vista Gestoría/Facturación/Facturas); NO se
duplican en ninguna hoja externa. Aquí solo se guarda el DOCUMENTO:

  · Drive si hay credenciales de ESCRITURA (google_drive con sa_b64/OAuth) → a
    `carpeta_facturas_raiz`/<año de la factura> (CLINICA/FACTURAS/2026…), o a `carpeta_facturas`;
  · si no, a `/media/facturas` (disco local, ya servido por la app en `/media`).

Si el correo no trae PDF (factura en el cuerpo/portal), se genera uno a partir del correo.
Si Drive falla, cae a local (nunca rompe el alta del gasto) y lo deja en el log: en oct-2026 las
carpetas configuradas llevaban semanas borradas y todo caía a local sin que nadie lo supiera.
"""
import logging
import re
from typing import Optional

from sqlmodel import Session, select

from application.services.gmail_ingest_service import MEDIA, _correo_a_pdf
from domain.models.config import Integracion
from domain.models.gestoria import Gasto
from infrastructure.external_apis import drive_client

log = logging.getLogger(__name__)


def _integ(session: Session, centro_id: int, tipo: str) -> Optional[dict]:
    ig = session.exec(select(Integracion).where(
        Integracion.centro_id == centro_id, Integracion.tipo == tipo)).first()
    return (ig.config or {}) if ig else None


def asegurar_pdf(email: dict, fuente) -> bytes:
    """Devuelve SIEMPRE bytes de un PDF. Si el adjunto/enlace ya es PDF, lo usa; si es una imagen
    (escaneo JPG/PNG), la envuelve en un PDF de una página; si no hay documento (factura en el
    cuerpo del correo), renderiza el correo a PDF. Así 'si no tuviera PDF, se crea'."""
    b = getattr(fuente, "bytes", b"") or b""
    if b[:5] == b"%PDF-":
        return b
    if b[:4] == b"\x89PNG" or b[:2] == b"\xff\xd8":
        try:
            import fitz
            img = fitz.open(stream=b, filetype="png" if b[:4] == b"\x89PNG" else "jpg")
            pdf = img.convert_to_pdf()
            img.close()
            return pdf
        except Exception:  # raiz: imagen rara → cae al render del correo de abajo
            pass
    return _correo_a_pdf(email)   # sin documento legible → PDF del propio correo


def _slug(s: Optional[str]) -> str:
    """'IMPLANT PROTESIS DENTAL 2004, S.L.' → 'IMPLANT-PROTESIS-DENTAL-2004-S-L' (sin tildes)."""
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "-", s.upper()).strip("-")[:80]


def _nombre(gasto: Gasto) -> str:
    """Mismo formato que la carpeta CLINICA/FACTURAS reorganizada (oct-2026):
    DD-MM-AAAA_PROVEEDOR_NUMERO.pdf, p.ej. 21-07-2026_IMPLANT-PROTESIS-DENTAL-2004-S-L_A-146574.pdf"""
    fecha = gasto.fecha.strftime("%d-%m-%Y") if gasto.fecha else "sin-fecha"
    return f"{fecha}_{_slug(gasto.proveedor_extraido) or 'PROVEEDOR'}_{_slug(gasto.numero_factura) or 'SN'}.pdf"


def _carpeta_destino(cfg: dict, gasto: Gasto) -> Optional[str]:
    """CLINICA/FACTURAS/<año de la factura> si está configurada la raíz (se crea el año si falta);
    si no, la carpeta fija de siempre."""
    raiz = cfg.get("carpeta_facturas_raiz")
    if raiz and gasto.fecha:
        anio = drive_client.buscar_o_crear_carpeta(cfg, str(gasto.fecha.year), raiz)
        return anio or raiz
    return cfg.get("carpeta_facturas") or (cfg.get("carpetas") or {}).get("procesadas") or cfg.get("folder_id")


def guardar_pdf(session: Session, centro_id: int, gasto: Gasto, email: dict, fuente) -> Optional[str]:
    """Guarda el PDF de la factura y fija `gasto.archivo_pdf_url`. Drive si hay escritura, si no local."""
    pdf = asegurar_pdf(email, fuente)
    if not pdf:
        return None
    nombre = _nombre(gasto)
    cfg = _integ(session, centro_id, "google_drive")
    if drive_client.configurado(cfg):                       # ESCRITURA disponible → Drive
        destino = _carpeta_destino(cfg, gasto)
        try:
            r = drive_client.subir(cfg, filename=nombre, content=pdf,
                                   mime="application/pdf", folder_id=destino)
            url = r.get("url") or (f"https://drive.google.com/file/d/{r['id']}/view" if r.get("id") else None)
            if url:
                gasto.archivo_pdf_url = url
                session.add(gasto)
                return url
            log.warning("archivado: Drive no devolvió enlace para el gasto %s (carpeta %s)", gasto.id, destino)
        except Exception as e:  # raiz: sin Drive → cae a local de abajo, sin romper el alta
            log.warning("archivado: Drive falló para el gasto %s (carpeta %s): %s", gasto.id, destino, str(e)[:200])
    MEDIA.mkdir(parents=True, exist_ok=True)                 # local
    (MEDIA / nombre).write_bytes(pdf)
    gasto.archivo_pdf_url = f"/media/facturas/{nombre}"
    session.add(gasto)
    return gasto.archivo_pdf_url
