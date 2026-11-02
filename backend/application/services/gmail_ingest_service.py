"""Servicio de email/Drive de Gestoría (capa de aplicación).

Tras eliminar la ingesta AUTOMÁTICA de facturas, este servicio mantiene lo que sigue vivo:
  · config de las integraciones (IMAP / Drive / LLM) + test/health,
  · visor de la factura (pdf_gasto / paginas_gasto: PDF de Drive o /media → imágenes),
  · CAPTURA del correo original (correo_pdf_gasto: abre el email por IMAP y lo renderiza a PDF),
  · reorganización de Drive por año.
"""
import re
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from domain.models.config import Integracion
from domain.models.gestoria import Gasto
from infrastructure.external_apis import drive_client, gmail_imap

MEDIA = Path(__file__).resolve().parents[2] / "media" / "facturas"

def _safe(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._\-]", "_", name)[:200]


def _pdf_a_imagenes(pdf_bytes: bytes, max_paginas: int = 2, dpi: int = 100) -> list[str]:
    """Renderiza las primeras páginas del PDF a JPEG base64 (para modelos de visión)."""
    import base64 as _b64
    try:
        import fitz  # pymupdf
    except ImportError:
        return []
    out = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in list(doc)[:max_paginas]:
            pix = page.get_pixmap(dpi=dpi)
            out.append(_b64.b64encode(pix.tobytes("jpeg")).decode())
        doc.close()
    except Exception:  # raiz: PDF ilegible/cifrado al rasterizar -> sin paginas para la IA; el correo se procesa sin ellas  # noqa: BLE001
        return []
    return out


def _correo_a_pdf(email: dict) -> bytes:
    """Renderiza un correo (cabecera + cuerpo HTML, o texto) a un PDF paginado con PyMuPDF.
    Es la 'captura del correo abierto': fiel al contenido, sin depender de Gmail web."""
    import html as _h
    import io

    import fitz
    asunto = _h.escape(email.get("asunto") or "(sin asunto)")
    de = _h.escape(email.get("remitente") or "")
    fecha = _h.escape(str(email.get("fecha") or ""))
    cabecera = (
        "<div style='font-family:Arial,sans-serif;border-bottom:2px solid #065AED;"
        "padding-bottom:8px;margin-bottom:12px'>"
        f"<div style='color:#065AED;font-size:15px;font-weight:bold'>{asunto}</div>"
        f"<div style='color:#555;font-size:11px'>De: {de} &nbsp;·&nbsp; {fecha}</div></div>")
    cuerpo = email.get("html")
    if not cuerpo:
        txt = _h.escape(email.get("cuerpo") or "(correo sin contenido legible)")
        cuerpo = f"<div style='font-family:Arial,sans-serif;font-size:12px;white-space:pre-wrap'>{txt}</div>"
    full = f"<div style='font-family:Arial,sans-serif'>{cabecera}{cuerpo}</div>"
    out = io.BytesIO()
    writer = fitz.DocumentWriter(out)
    story = fitz.Story(html=full)
    media = fitz.paper_rect("a4")
    rect = media + (36, 36, -36, -36)
    more, paginas = 1, 0
    while more and paginas < 40:          # tope de seguridad ante HTML patológico
        dev = writer.begin_page(media)
        more, _ = story.place(rect)
        story.draw(dev)
        writer.end_page()
        paginas += 1
    writer.close()
    return out.getvalue()


class GmailIngestService:
    def __init__(self, session: Session):
        self.session = session
        self._cache_anyo: dict = {}  # año → id de subcarpeta dentro de 'Facturas procesadas'

    # ── Config de integraciones ──
    def _integ(self, centro_id: int, tipo: str) -> Optional[Integracion]:
        return self.session.exec(select(Integracion).where(
            Integracion.centro_id == centro_id, Integracion.tipo == tipo)).first()

    def get_config(self, centro_id: int) -> dict:
        imap = self._integ(centro_id, "email_imap")
        drive = self._integ(centro_id, "google_drive")
        cfg = dict(imap.config or {}) if imap else {}
        cfg.pop("password", None)
        return {"activo": imap.activo if imap else False, "config": cfg,
                "driveListo": drive_client.configurado(drive.config if drive else None)}

    def save_config(self, centro_id: int, data: dict) -> dict:
        ig = self._integ(centro_id, "email_imap")
        if not ig:
            ig = Integracion(centro_id=centro_id, tipo="email_imap", nombre="Gmail IMAP", config={})
        cfg = dict(ig.config or {})
        for k in ("host", "port", "usuario", "carpeta", "dias"):
            if k in data and data[k] is not None:
                cfg[k] = data[k]
        if data.get("password"):
            # App passwords de Google pegadas con espacios ('xxxx xxxx…') → 535 BadCredentials.
            cfg["password"] = data["password"].replace(" ", "")
        ig.config = cfg
        if "activo" in data:
            ig.activo = bool(data["activo"])
        self.session.add(ig); self.session.commit()
        return self.get_config(centro_id)

    def test(self, centro_id: int) -> dict:
        ig = self._integ(centro_id, "email_imap")
        if not ig or not ig.config:
            return {"ok": False, "error": "Sin configuración IMAP"}
        return gmail_imap.test_connection(ig.config)


    def _carpeta_anyo(self, drive_cfg, procesadas_id, anyo) -> Optional[str]:
        """Subcarpeta 'AAAA' dentro de 'Facturas procesadas' (cacheada). None si no aplica/falla."""
        if not anyo or not (2000 <= anyo <= 2100):
            return None
        if anyo not in self._cache_anyo:
            self._cache_anyo[anyo] = drive_client.buscar_o_crear_carpeta(drive_cfg, str(anyo), procesadas_id)
        return self._cache_anyo[anyo]

    def reorganizar_drive_por_anyo(self, centro_id: int) -> dict:
        """Mueve las facturas ya subidas a 'Facturas procesadas' a su subcarpeta por año.
        Mover conserva el id/enlace del fichero, así que no rompe los archivo_pdf_url guardados."""
        import re as _re
        drive_ig = self._integ(centro_id, "google_drive")
        if not (drive_ig and drive_client.configurado(drive_ig.config)):
            return {"ok": False, "error": "Drive no configurado"}
        cfg = drive_ig.config
        procesadas_id = (cfg.get("carpetas") or {}).get("procesadas")
        if not procesadas_id:
            return {"ok": False, "error": "Sin carpeta 'procesadas'"}
        gastos = self.session.exec(select(Gasto).where(
            Gasto.centro_id == centro_id, Gasto.archivo_pdf_url.like("%drive.google.com%"))).all()
        movidos = fallos = 0
        for g in gastos:
            anyo = g.fecha.year
            destino = self._carpeta_anyo(cfg, procesadas_id, anyo)
            if not destino:
                continue
            fid = _re.search(r"/d/([^/]+)", g.archivo_pdf_url or "")
            if not fid:
                continue
            # mueve desde 'procesadas' a 'procesadas/AAAA' (si ya está en el año, addParents es idempotente)
            if drive_client.mover_fichero(cfg, fid.group(1), destino, procesadas_id):
                movidos += 1
            else:
                fallos += 1
        return {"ok": True, "movidos": movidos, "fallos": fallos, "carpetasAnyo": list(self._cache_anyo.keys())}

    # ── apoyos ──
    def _llm_cfg(self, centro_id: int) -> Optional[dict]:
        from application.services.llm_config import GESTORIA_FACTURAS, resolver_llm
        c = resolver_llm(self.session, centro_id, GESTORIA_FACTURAS)
        return c if c and c.get("base_url") and c.get("model") else None


    def pdf_gasto(self, centro_id: int, gid: int) -> Optional[bytes]:
        """Devuelve los bytes del PDF de una factura (descargado de Drive o leído de /media).
        Sirve para mostrarlo con el visor nativo del navegador (scroll/zoom/pan completos)."""
        g = self.session.get(Gasto, gid)
        if not g or g.centro_id != centro_id or not g.archivo_pdf_url:
            return None
        url = g.archivo_pdf_url
        if "drive.google.com" in url:
            m = re.search(r"/d/([^/]+)", url)
            drive_ig = self._integ(centro_id, "google_drive")
            if not (m and drive_ig and drive_client.configurado(drive_ig.config)):
                return None
            return drive_client.descargar(drive_ig.config, m.group(1))
        if "/media/facturas/" in url:
            local = MEDIA / url.split("/media/facturas/")[-1]
            try:
                return local.read_bytes()
            except Exception:  # raiz: fichero local de factura ausente/ilegible -> None (sin adjunto), el correo sigue  # noqa: BLE001
                return None
        return None

    def correo_pdf_gasto(self, centro_id: int, gid: int) -> Optional[bytes]:
        """Abre el correo ORIGINAL del gasto por IMAP y lo renderiza a PDF (captura del correo).
        Para las facturas en 'revisar' que solo tienen el enlace al correo (sin PDF adjunto).
        None si no hay correo asociado, IMAP no está disponible o el correo no se encuentra."""
        g = self.session.get(Gasto, gid)
        if (not g or g.centro_id != centro_id or not g.gmail_message_id
                or g.gmail_message_id.startswith("upload:")):
            return None
        ig = self._integ(centro_id, "email_imap")
        if not (ig and ig.config):
            return None
        try:
            email = gmail_imap.fetch_por_message_id(ig.config, g.gmail_message_id)
        except Exception:  # raiz: IMAP caido/credenciales -> None; el caller decide si el correo se omite  # noqa: BLE001
            return None
        return _correo_a_pdf(email) if email else None

    def paginas_gasto(self, centro_id: int, gid: int) -> dict:
        """Devuelve las páginas de la factura como imágenes (data-url) para un visor con
        arrastre/zoom propio (la 'mano' que agarra el documento)."""
        contenido = self.pdf_gasto(centro_id, gid)
        if not contenido:
            contenido = self.correo_pdf_gasto(centro_id, gid)   # sin PDF → captura del correo original
        if not contenido:
            return {"paginas": []}
        if contenido[:5] == b"%PDF-":
            imgs = _pdf_a_imagenes(contenido, max_paginas=10, dpi=170)
            return {"paginas": [f"data:image/jpeg;base64,{b}" for b in imgs]}
        import base64 as _b64
        return {"paginas": [f"data:image/jpeg;base64,{_b64.b64encode(contenido).decode()}"]}

    def health(self, centro_id: int) -> dict:
        """Estado del proceso de facturas: saludable o con incidencia."""
        imap = self._integ(centro_id, "email_imap")
        drive = self._integ(centro_id, "google_drive")
        llm = self._llm_cfg(centro_id)
        imap_ok = bool(imap and (imap.config or {}).get("usuario"))
        drive_ok = drive_client.configurado(drive.config if drive else None)
        # ¿el modelo RESPONDE? Antes bastaba con que hubiera clave escrita, y por eso el
        # panel dio "Operativa" durante horas con el modelo retirado por el proveedor.
        from application.services.llm_salud import estado_llm
        salud_ia = estado_llm(llm)
        en_revisar = self.session.exec(select(Gasto).where(
            Gasto.centro_id == centro_id, Gasto.estado == "revisar")).all()
        n_rev = len(en_revisar)
        problemas = []
        if not imap_ok:
            problemas.append("Gmail sin configurar")
        if not drive_ok:
            problemas.append("Drive sin configurar")
        if salud_ia["ok"] is not True:
            problemas.append(f"IA: {salud_ia['motivo']}")
        estado = "incidencia" if problemas else "ok"
        return {"estado": estado, "imapOk": imap_ok, "driveOk": drive_ok,
                "iaOk": salud_ia["ok"] is True, "iaMotivo": salud_ia["motivo"],
                "iaModelo": salud_ia["modelo"],
                "enRevisar": n_rev, "problemas": problemas}

