"""Envío de email vía la integración SMTP del centro (Configuración · email_saliente).

Si no hay SMTP configurada o falla, devuelve False (el que llama decide el fallback).
Nunca lanza.
"""
import smtplib
import ssl
from email.mime.text import MIMEText

from sqlmodel import Session, select

from domain.models.config import Integracion


def send_email(session: Session, to: str, subject: str, html: str) -> bool:
    it = session.exec(select(Integracion).where(Integracion.tipo == "email_saliente")).first()
    cfg = (it.config if it else None) or {}
    host = cfg.get("smtp_host")
    if not host:
        return False
    try:
        port = int(cfg.get("puerto") or 587)
        user, pw = cfg.get("usuario"), cfg.get("password")
        remitente = cfg.get("direccion") or cfg.get("remitente") or user or "no-reply@localhost"
        msg = MIMEText(html, "html", "utf-8")
        msg["Subject"], msg["From"], msg["To"] = subject, remitente, to
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls(context=ssl.create_default_context())
            if user and pw:
                s.login(user, pw)
            s.sendmail(remitente, [to], msg.as_string())
        return True
    except Exception:
        return False
