"""Cliente IMAP para ingesta de facturas (infraestructura). stdlib imaplib + email + pypdf.

Maneja los 3 casos: correo con adjunto (PDF/XML), sin adjunto (cuerpo HTML/texto) y
con enlace de descarga. Descarga de enlaces con guarda anti-SSRF (no IPs privadas).
"""
import email
import imaplib
import io
import ipaddress
import re
import socket
from datetime import date, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from domain.services import invoice_extractor as ext

DEFAULTS = {"host": "imap.gmail.com", "port": 993, "carpeta": "INBOX", "dias": 30}


def _cfg(c: dict, k: str) -> Any:
    v = c.get(k)
    return v if v not in (None, "") else DEFAULTS.get(k)


def _salir(cli) -> None:
    """Logout best-effort para los `finally`: si ya cayó, no hay nada que cerrar."""
    try:
        cli.logout()
    except Exception:  # raiz: el logout en finally nunca tiene plan B
        pass


def _decode(s: Optional[str]) -> str:
    if not s:
        return ""
    return "".join(p.decode(e or "utf-8", "replace") if isinstance(p, bytes) else p
                   for p, e in decode_header(s))


def _connect(cfg: dict) -> imaplib.IMAP4_SSL:
    cli = imaplib.IMAP4_SSL(_cfg(cfg, "host"), int(_cfg(cfg, "port")))
    cli.login(cfg["usuario"], cfg["password"])
    return cli



def _carpeta_imap(nombre: str) -> str:
    """Nombre de carpeta listo para SELECT/MOVE. Con espacios ("Facturas/Facturas revisadas")
    sin comillas Gmail responde BAD 'Could not parse command': el 21-sep-2026 eso dejó de
    mover los correos procesados y la ingesta quedó atascada. Una sola regla para todos."""
    if " " in nombre and not (nombre.startswith('"') and nombre.endswith('"')):
        return f'"{nombre}"'
    return nombre

def test_connection(cfg: dict) -> dict:
    if not cfg.get("usuario") or not cfg.get("password"):
        return {"ok": False, "error": "Faltan usuario o contraseña"}
    try:
        cli = _connect(cfg)
        cli.select(_carpeta_imap(_cfg(cfg, "carpeta")), readonly=True)
        cli.logout()
        return {"ok": True, "cuenta": cfg["usuario"]}
    except Exception as e:  # raiz: conexion IMAP o credenciales invalidas al comprobar la cuenta -> {ok:False, error}; nunca propaga  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(content)).pages)
    except Exception:  # raiz: PDF adjunto ilegible/cifrado -> sin texto nativo; el correo se procesa igual  # noqa: BLE001
        return ""


def _text(part: Any) -> str:
    return (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")


def _html_a_texto(html: str) -> str:
    txt = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    txt = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", txt)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&").replace("&euro;", "€")
              .replace("&aacute;", "á").replace("&eacute;", "é").replace("&iacute;", "í")
              .replace("&oacute;", "ó").replace("&uacute;", "ú").replace("&ntilde;", "ñ"))
    return re.sub(r"[ \t]+", " ", txt).strip()


def _es_destino_privado(host: str) -> bool:
    """True si el host resuelve a CUALQUIER IP no pública. Usa getaddrinfo (IPv4+IPv6),
    no gethostbyname (que solo ve IPv4 y deja colar [::1]/hosts con solo registro AAAA)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:  # raiz: el host del enlace no resuelve -> se trata como inseguro (True); cierra, no abre  # noqa: BLE001
        return True  # si no resuelve, lo tratamos como inseguro
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except Exception:  # raiz: la IP resuelta no es parseable -> se trata como insegura (True); cierra, no abre  # noqa: BLE001
            return True
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return True
    return False


def descargar_enlace(url: str, _max_redirects: int = 5) -> Optional[dict]:
    """Descarga un enlace de factura con guarda anti-SSRF: valida el host en CADA salto de
    redirección (no solo el inicial), así una URL pública no puede redirigir a 169.254.169.254
    ni a la red interna. Devuelve {content, content_type, filename}.
    Residual conocido: queda una ventana TOCTOU entre el getaddrinfo de la validación y la
    conexión real de httpx (DNS rebinding puro); cerrarlo requeriría fijar la IP resuelta."""
    try:
        with httpx.Client(follow_redirects=False, timeout=15) as cli:
            for _ in range(_max_redirects + 1):
                host = urlparse(url).hostname or ""
                if not host or _es_destino_privado(host):
                    return None
                r = cli.get(url)
                if r.is_redirect:
                    loc = r.headers.get("location")
                    if not loc:
                        return None
                    url = str(httpx.URL(url).join(loc))  # resuelve relativas
                    continue
                if r.status_code != 200:
                    return None
                ct = (r.headers.get("content-type") or "").lower()
                fn = (urlparse(str(r.url)).path.split("/")[-1] or "enlace")[:200]
                return {"content": r.content, "content_type": ct, "filename": fn}
        return None  # demasiadas redirecciones
    except Exception:  # raiz: descarga del enlace falla (red/HTTP/host privado o redirecciones) -> None; el enlace se omite  # noqa: BLE001
        return None


def _parse_message(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw)
    asunto = _decode(msg.get("Subject"))
    remitente = _decode(msg.get("From"))
    try:
        fecha = parsedate_to_datetime(msg.get("Date")).date()
    except Exception:  # raiz: cabecera Date ilegible o ausente -> se usa la fecha de hoy  # noqa: BLE001
        fecha = date.today()
    cuerpo, html, pdf_texto, adjuntos = "", "", "", []
    for part in msg.walk():
        ctype = (part.get_content_type() or "").lower()
        disp = (part.get("Content-Disposition") or "").lower()
        if part.is_multipart():
            continue
        if "attachment" in disp or ctype in ("application/pdf", "text/xml", "application/xml"):
            payload = part.get_payload(decode=True) or b""
            fn = _decode(part.get_filename()) or "adjunto"
            adjuntos.append({"filename": fn, "content": payload, "content_type": ctype})
            if ctype == "application/pdf" or fn.lower().endswith(".pdf"):
                pdf_texto += "\n" + _pdf_text(payload)
        elif ctype == "text/plain" and not cuerpo:
            cuerpo = _text(part)
        elif ctype == "text/html" and not html:
            html = _text(part)
    enlaces = ext.enlaces_factura(html) if html else []
    if not cuerpo and html:
        cuerpo = _html_a_texto(html)
    return {"remitente": remitente, "asunto": asunto, "fecha": fecha, "cuerpo": cuerpo,
            "html": html, "pdf_texto": pdf_texto.strip(), "adjuntos": adjuntos, "enlaces": enlaces}


def listar_carpeta_msgids(cfg: dict, carpeta: str) -> list[dict]:
    """Lista TODOS los mensajes de una carpeta como {uid, msg_id} (solo cabecera Message-ID).

    Barato: una búsqueda ALL + FETCH del Message-ID en bloques de 200 (no baja cuerpos ni
    adjuntos). Para el driver de ingesta del buzón, que primero decide qué correos son nuevos
    y solo entonces baja los que hay que procesar."""
    cli = _connect(cfg)
    try:
        typ, _ = cli.select(f'"{carpeta}"', readonly=True)
        if typ != "OK":
            return []
        typ, data = cli.uid("search", None, "ALL")
        if typ != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        out: list[dict] = []
        for i in range(0, len(uids), 200):
            chunk = b",".join(uids[i:i + 200])
            typ, resp = cli.uid("fetch", chunk, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
            if typ != "OK":
                continue
            cur_uid = None
            for item in resp:
                if not isinstance(item, tuple):
                    continue
                m = re.search(rb"UID (\d+)", item[0] or b"")
                cur_uid = m.group(1).decode() if m else cur_uid
                mid = _msg_id([item])
                if cur_uid:
                    out.append({"uid": cur_uid, "msg_id": (mid or "").strip()})
        return out
    finally:
        _salir(cli)


def _carpeta_todos(cli) -> Optional[str]:
    """Carpeta 'Todos los mensajes' de Gmail (atributo \\All, independiente del idioma). Contiene
    TODOS los correos, incluidos los archivados (que ya NO están en INBOX) → imprescindible para
    encontrar los del backlog por su Message-ID."""
    try:
        typ, boxes = cli.list()
        if typ != "OK":
            return None
        for b in boxes or []:
            line = b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b)
            if "\\All" in line:
                m = re.search(r'"([^"]+)"\s*$', line)        # el nombre va entre comillas al final
                if m:
                    return m.group(1)
    except Exception:  # raiz: listado de carpetas IMAP falla o formato inesperado -> None (sin carpeta especial detectada)  # noqa: BLE001
        return None
    return None


def fetch_por_message_id(cfg: dict, message_id: str, carpeta: Optional[str] = None) -> Optional[dict]:
    """Abre UN correo por su Message-ID (RFC822). Devuelve el dict de `_parse_message` + uid +
    labels (etiquetas Gmail X-GM-LABELS, p.ej. '\\Sent'). None si no se encuentra.
    Lo usa el re-proceso del backlog (bucket C) y la captura del correo, releyendo el original.
    Busca en 'Todos los mensajes' (\\All) por defecto: los del backlog están archivados, no en INBOX."""
    if not message_id:
        return None
    mid = message_id.strip()
    cli = _connect(cfg)
    try:
        # La carpeta puede traer espacios ("Gastos/2. Gastos Procesados"): sin comillas el
        # SELECT da BAD 'Could not parse command' y el correo parece "no encontrado".
        _sel = carpeta or _carpeta_todos(cli) or _cfg(cfg, "carpeta") or "INBOX"
        cli.select(_carpeta_imap(_sel), readonly=True)
        uids: list[bytes] = []
        for needle in (mid, mid.strip("<>"), f"<{mid.strip('<>')}>"):
            typ, data = cli.search(None, "HEADER", "Message-ID", needle)
            if typ == "OK" and data and data[0].split():
                uids = data[0].split()
                break
        if not uids:
            return None
        uid = uids[-1]
        typ, raw = cli.fetch(uid, "(RFC822)")
        if typ != "OK" or not raw or not raw[0]:
            return None
        m = _parse_message(raw[0][1])
        m["uid"] = uid.decode()
        m["msg_id"] = mid
        # Etiquetas Gmail (para detectar \Sent). No todos los servidores las exponen → best-effort.
        labels: list[str] = []
        try:
            typ, lab = cli.fetch(uid, "(X-GM-LABELS)")
            if typ == "OK" and lab and lab[0]:
                txt = lab[0].decode("utf-8", "replace") if isinstance(lab[0], bytes) else str(lab[0])
                trozo = txt.split("X-GM-LABELS", 1)[-1]
                labels = [s.strip('"') for s in re.findall(r'\\?\w[\w/]*|"[^"]+"', trozo)]
        except Exception:  # raiz: X-GM-LABELS no legible en la respuesta IMAP -> lista de etiquetas vacia  # noqa: BLE001
            labels = []
        m["labels"] = labels
        return m
    finally:
        _salir(cli)


def mover(cfg: dict, origen: str, uids: list[str], destino: str) -> int:
    """Mueve correos (por UID) de `origen` a `destino`. Gmail: UID MOVE; fallback COPY+borrar."""
    if not uids:
        return 0
    cli = _connect(cfg)
    movidos = 0
    dest = _carpeta_imap(destino)
    try:
        cli.select(_carpeta_imap(origen))  # escritura (no readonly)
        for uid in uids:
            typ, _ = cli.uid("MOVE", uid, dest)
            if typ != "OK":
                cli.uid("COPY", uid, dest)
                cli.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
            movidos += 1
        cli.expunge()
        return movidos
    finally:
        _salir(cli)


def _msg_id(data: Any) -> Optional[str]:
    try:
        for item in data:
            if isinstance(item, tuple) and item[1]:
                txt = item[1].decode("utf-8", "replace")
                line = txt.split(":", 1)[1].strip() if ":" in txt else txt.strip()
                if line:
                    return line
    except Exception:  # raiz: cabecera rota → sin Message-Id (None), no se indexa
        pass
    return None
