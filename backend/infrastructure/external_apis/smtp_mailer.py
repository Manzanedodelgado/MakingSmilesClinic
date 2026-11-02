"""Envío de email por SMTP (lee integraciones.email_saliente). smtplib stdlib, STARTTLS."""
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional


def send_html(cfg: dict, *, to: str, subject: str, html: str, reply_to: Optional[str] = None,
              attachments: Optional[list[dict]] = None) -> dict:
    """Envía un HTML y, opcionalmente, adjuntos: [{filename, content: bytes, mimetype?}]."""
    if not cfg.get("usuario") or not cfg.get("password"):
        return {"ok": False, "error": "SMTP no configurado"}
    if not to:
        return {"ok": False, "error": "Falta el destinatario"}
    # "mixed" si hay adjuntos (cuerpo + ficheros); "alternative" para solo HTML.
    msg = MIMEMultipart("mixed" if attachments else "alternative")
    msg["From"] = f"{cfg.get('remitente', '')} <{cfg.get('direccion') or cfg['usuario']}>".strip()
    msg["To"] = to
    msg["Subject"] = subject
    rt = reply_to or cfg.get("responder_a")
    if rt:
        msg["Reply-To"] = rt
    msg.attach(MIMEText(html, "html", "utf-8"))
    for a in (attachments or []):
        maintype, _, subtype = (a.get("mimetype") or "text/csv").partition("/")
        content = a["content"]
        if isinstance(content, str):
            content = content.encode("utf-8")
        part = MIMEApplication(content, _subtype=subtype or "octet-stream")
        part.add_header("Content-Disposition", "attachment", filename=a["filename"])
        msg.attach(part)
    try:
        with _connect(cfg) as s:
            s.send_message(msg)
        return {"ok": True, "destino": to}
    except Exception as e:  # raiz: SMTP caído -> error devuelto, no lanza
        return {"ok": False, "error": str(e)}


def _connect(cfg: dict) -> smtplib.SMTP:
    s = smtplib.SMTP(cfg.get("smtp_host") or "smtp.gmail.com", int(cfg.get("puerto") or 587), timeout=20)
    s.ehlo()
    s.starttls(context=ssl.create_default_context())
    s.login(cfg["usuario"], cfg["password"])
    return s
