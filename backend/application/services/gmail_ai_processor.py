"""
GmailAIProcessor — Procesador de emails de facturas en tiempo real (push Gmail).

Recibe webhook de Gmail → fetch email completo (IMAP) → prepara payload multimodal
→ llama a IA multimodal (Gemini 2.5 Flash via OpenRouter) → valida respuesta
→ registra en BD (Gasto + Proveedor) → sube PDF a Drive → mueve email → emite WebSocket.
"""

import asyncio
import base64
import hashlib
import json
import logging
import io
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import httpx
from sqlmodel import Session, select

from api.auth_deps import CurrentUser
from domain.config.ia_multimodal import (
    DEFAULT_CONFIG,
    ModeloMultimodalConfig,
    obtener_config_centro,
)
from domain.models.config import Integracion
from domain.models.gestoria import Gasto, Proveedor
from domain.prompts.gasto_multimodal import FEW_SHOTS, SYSTEM_PROMPT
from domain.schemas.gmail_ai import GastoIAResponse
from infrastructure.config.db import get_session
from application.services.intake_service import (CARPETA_ENTRADA, CARPETA_PAPELERA,
                                                 ETIQUETA_INCIDENCIAS, ETIQUETA_PROCESADAS,
                                                 ETIQUETA_REVISADAS)
from infrastructure.external_apis import drive_client, gmail_imap
from infrastructure.external_apis.llm_client import LLMClient, LLMError

logger = logging.getLogger(__name__)


@dataclass
class EmailCompleto:
    """Email con todos sus componentes listos para IA."""
    message_id: str
    uid: str
    remitente: str
    asunto: str
    fecha: date
    cuerpo_texto: str
    cuerpo_html: str
    adjuntos: list[dict]  # [{filename, content, mime_type}]
    enlaces: list[tuple[str, str]]  # [(url, texto_visible)]


@dataclass
class ProcesamientoResultado:
    """Resultado del procesamiento de un email."""
    ok: bool
    accion: str  # gasto | incidencia | descartado | duplicado | error
    gasto_id: Optional[int] = None
    proveedor_id: Optional[int] = None
    drive_url: Optional[str] = None
    error: Optional[str] = None
    detalles: Optional[str] = None


class GmailAIProcessor:
    """
    Procesa emails de facturas usando IA multimodal en tiempo real.
    
    Flujo:
    1. Recibe message_id del webhook Gmail
    2. Fetch email completo via IMAP (incluye adjuntos)
    3. Prepara payload multimodal (texto + PDFs + imágenes)
    4. Llama a IA (Gemini 2.5 Flash via OpenRouter) con structured output
    5. Valida respuesta con Pydantic (GastoIAResponse)
    6. Deduplica (CIF + nº factura + total)
    7. Registra/actualiza Gasto + Proveedor en tablas principales
    8. Sube PDF a Drive / genera PDF si no hay adjunto
    9. Mueve email a "Facturas/Facturas Procesadas" o "Incidencias"
    10. Emite evento WebSocket para UI tiempo real
    """

    def __init__(self, session: Session, centro_id: int):
        self.session = session
        self.centro_id = centro_id
        self.config_ia = obtener_config_centro(centro_id, session)
        self.imap_config = self._get_imap_config()
        self.drive_config = self._get_drive_config()
        self.openrouter_key = self._get_openrouter_key()
        self.relevos = self._get_relevos()

    def _get_imap_config(self) -> Optional[dict]:
        ig = self.session.exec(select(Integracion).where(
            Integracion.centro_id == self.centro_id,
            Integracion.tipo == "email_imap",
            Integracion.activo == True
        )).first()
        return ig.config if ig else None

    def _get_drive_config(self) -> Optional[dict]:
        ig = self.session.exec(select(Integracion).where(
            Integracion.centro_id == self.centro_id,
            Integracion.tipo == "google_drive",
            Integracion.activo == True
        )).first()
        return ig.config if ig else None

    def _get_openrouter_key(self) -> Optional[str]:
        ig = self.session.exec(select(Integracion).where(
            Integracion.centro_id == self.centro_id,
            Integracion.tipo == "llm",
            Integracion.agente == "gestor_multimodal",
            Integracion.activo == True
        )).first()
        if ig and ig.config:
            return ig.config.get("api_key") or ig.config.get("openrouter_api_key")
        return None

    def _get_relevos(self) -> list[dict]:
        """Plan B de proveedores (cadena de rescate) de la misma integración
        `gestor_multimodal`, nuevo campo opcional `relevos` — retrocompatible con la
        integración real de hoy, que no lo tiene (lista vacía)."""
        ig = self.session.exec(select(Integracion).where(
            Integracion.centro_id == self.centro_id,
            Integracion.tipo == "llm",
            Integracion.agente == "gestor_multimodal",
            Integracion.activo == True
        )).first()
        if ig and ig.config:
            return ig.config.get("relevos") or []
        return []

    # ═══════════════════════════════════════════════════════════════════════
    # ENTRADA PRINCIPAL: PROCESAR WEBHOOK
    # ═══════════════════════════════════════════════════════════════════════

    async def procesar_webhook(self, message_id: str) -> ProcesamientoResultado:
        """Procesa un email recibido via webhook Gmail."""
        try:
            # 1. Fetch email completo via IMAP
            email = await self._fetch_email_completo(message_id)
            if not email:
                return ProcesamientoResultado(ok=False, accion="error", error="Email no encontrado")

            # 2. Preparar contenido multimodal para IA
            payload_multimodal = self._preparar_payload_multimodal(email)

            # 3. Llamar a IA multimodal
            respuesta_ia = await self._llamar_ia_multimodal(payload_multimodal)
            if not respuesta_ia:
                return ProcesamientoResultado(ok=False, accion="error", error="IA no respondió")

            # 3b. I7 (revisión final de rama): comprobación mínima ANTES de Pydantic. El
            # `model_validator` de GastoIAResponse ya exige cif_emisor/total no-None cuando
            # accion="gasto" (ver validar_coherencia_gasto), pero no rechaza cadena vacía
            # ("") ni 0 explícito — huecos que un relevo sin capacidad de visión real
            # (futuro riesgo señalado en el spec) podría colar devolviendo "gasto" sin
            # haber leído nada. Si pasa esto, se trata igual que un None/error de la IA:
            # no se registra, queda para revisión manual (vía el "IA no respondió" ya
            # existente). Arreglo mínimo, sin rediseñar el camino webhook.
            if respuesta_ia.get("accion") == "gasto" and (
                not str(respuesta_ia.get("cif_emisor") or "").strip()
                or not respuesta_ia.get("total")
            ):
                logger.warning(
                    "IA devolvió accion='gasto' sin cif_emisor/total utilizables; "
                    "se trata como no fiable, no se registra: %s", message_id
                )
                return ProcesamientoResultado(
                    ok=False, accion="error",
                    error="gasto sin cif_emisor/total: requiere revisión manual"
                )

            # 4. Validar respuesta con Pydantic
            try:
                datos_validados = GastoIAResponse(**respuesta_ia)
            except Exception as e:  # raiz: la respuesta de la IA no valida el esquema Pydantic -> resultado error de validacion, no se propaga
                logger.error(f"Validación Pydantic falló: {e}")
                return ProcesamientoResultado(ok=False, accion="error", error=f"Validación IA: {e}")

            # 5. Procesar según clasificación
            return await self._procesar_clasificacion(email, datos_validados)

        except Exception as e:  # raiz: fallo no previsto procesando el webhook (IA/BD) -> resultado error con traza; nunca 500 crudo
            logger.exception(f"Error procesando webhook {message_id}: {e}")
            return ProcesamientoResultado(ok=False, accion="error", error=str(e))

    # ═══════════════════════════════════════════════════════════════════════
    # FETCH EMAIL COMPLETO (IMAP)
    # ═══════════════════════════════════════════════════════════════════════

    async def _fetch_email_completo(self, message_id: str) -> Optional[EmailCompleto]:
        """Obtiene email completo con adjuntos via IMAP."""
        if not self.imap_config:
            logger.error("IMAP no configurado")
            return None

        try:
            # Carpetas REALES del buzón (verificadas 2026-08-09, cf. intake_service
            # ETIQUETA_*). Antes se buscaba en "Gastos/N. …", una nomenclatura anterior que
            # no existe: el fetch solo encontraba el correo si estaba en INBOX, mientras que
            # al mover se escribía en "Facturas/…" — incoherente consigo mismo.
            carpetas = [CARPETA_ENTRADA, ETIQUETA_INCIDENCIAS, ETIQUETA_REVISADAS,
                        ETIQUETA_PROCESADAS]
            
            for carpeta in carpetas:
                email_data = gmail_imap.fetch_por_message_id(self.imap_config, message_id, carpeta=carpeta)
                if email_data:
                    return self._parsear_email_gmail(email_data, message_id, carpeta)
            
            logger.warning(f"Email {message_id} no encontrado en ninguna carpeta")
            return None
        except Exception as e:  # raiz: fetch del correo falla (IMAP/credenciales) -> None y el correo se omite
            logger.error(f"Error fetch email {message_id}: {e}")
            return None

    def _parsear_email_gmail(self, email_data: dict, message_id: str, carpeta: str) -> EmailCompleto:
        """Convierte lo que devuelve gmail_imap.fetch_por_message_id a EmailCompleto.

        22-oct-2026: este metodo esperaba el formato de la API de Gmail
        (payload.headers[], body.data en base64url, parts[] anidadas), pero quien lo
        llama es _fetch_email_completo, que usa IMAP y devuelve un dict PLANO:
        {remitente, asunto, fecha, cuerpo, html, pdf_texto, adjuntos, enlaces}.
        Resultado: .get("payload", {}) daba vacio y TODOS los campos salian en blanco,
        asi que la IA recibia un correo sin asunto, sin remitente y sin adjuntos, y lo
        descartaba. 827 correos esperando y 0 extraidos.

        El texto ya extraido de los PDFs (pdf_texto) se anexa al cuerpo: es lo que
        lleva los importes cuando la factura viene como adjunto.
        """
        fecha = email_data.get("fecha")
        if not isinstance(fecha, date):
            from email.utils import parsedate_to_datetime
            try:
                fecha = parsedate_to_datetime(str(fecha)).date()
            except Exception:  # raiz: fecha del correo ilegible -> se usa la fecha de hoy
                fecha = date.today()

        cuerpo_texto = email_data.get("cuerpo") or ""
        pdf_texto = email_data.get("pdf_texto") or ""
        if pdf_texto:
            cuerpo_texto = cuerpo_texto + "\n\n--- TEXTO DE LOS ADJUNTOS ---\n" + pdf_texto

        # gmail_imap nombra el tipo "content_type"; EmailCompleto espera "mime_type".
        adjuntos = []
        for a in (email_data.get("adjuntos") or []):
            adjuntos.append({
                "filename": a.get("filename", ""),
                "content": a.get("content", b""),
                "mime_type": a.get("mime_type") or a.get("content_type", ""),
            })

        # EmailCompleto.enlaces son pares (url, texto_visible) y _descargar_enlaces
        # los desempaqueta asi; gmail_imap devuelve cadenas sueltas, de modo que
        # pasarlas tal cual rompia con "too many values to unpack".
        enlaces = []
        for e in (email_data.get("enlaces") or []):
            if isinstance(e, str):
                enlaces.append((e, ""))
            elif isinstance(e, (list, tuple)) and len(e) >= 2:
                enlaces.append((e[0], e[1]))
        if not enlaces:
            enlaces = self._extraer_enlaces_html(email_data.get("html") or "")

        return EmailCompleto(
            message_id=message_id,
            uid=str(email_data.get("uid", "")),
            remitente=email_data.get("remitente", ""),
            asunto=email_data.get("asunto", ""),
            fecha=fecha,
            cuerpo_texto=cuerpo_texto,
            cuerpo_html=email_data.get("html") or "",
            adjuntos=adjuntos,
            enlaces=enlaces,
        )

    def _extraer_cuerpos(self, payload: dict) -> tuple[str, str]:
        """Extrae text/plain y text/html recursivamente."""
        textos, htmls = [], []
        
        def recorrer(parte):
            mime = parte.get("mimeType", "")
            data = parte.get("body", {}).get("data")
            if data:
                try:
                    import base64
                    contenido = base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
                except Exception:  # raiz: parte MIME en base64 corrupta -> contenido vacio para esa parte; el resto del cuerpo se lee
                    contenido = ""
                if mime == "text/plain":
                    textos.append(contenido)
                elif mime == "text/html":
                    htmls.append(contenido)
            for sub in parte.get("parts", []):
                recorrer(sub)
        
        recorrer(payload)
        return "\n".join(textos), "\n".join(htmls)

    def _extraer_adjuntos(self, email_data: dict) -> list[dict]:
        """Descarga todos los adjuntos del email."""
        adjuntos = []
        payload = email_data.get("payload", {})
        
        def recorrer(parte):
            filename = parte.get("filename")
            mime_type = parte.get("mimeType", "")
            body = parte.get("body", {})
            att_id = body.get("attachmentId")
            data_directa = body.get("data")
            
            if filename and (att_id or data_directa):
                try:
                    if att_id:
                        attachment = gmail_imap.descargar_adjunto(self.imap_config, email_data["id"], att_id)
                        content = attachment.get("content", b"")
                    else:
                        import base64
                        content = base64.urlsafe_b64decode(data_directa.encode("UTF-8"))
                    
                    adjuntos.append({
                        "filename": filename,
                        "content": content,
                        "mime_type": mime_type or self._guess_mime(filename)
                    })
                except Exception as e:  # raiz: adjunto no descargable (base64/Drive) -> se omite y se sigue con los demas
                    logger.warning(f"Error descargando adjunto {filename}: {e}")
            
            for sub in parte.get("parts", []):
                recorrer(sub)
        
        recorrer(payload)
        return adjuntos

    def _extraer_enlaces_html(self, html: str) -> list[tuple[str, str]]:
        """Extrae (url, texto_visible) de enlaces en HTML."""
        if not html:
            return []
        import re
        enlaces = re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S)
        resultado = []
        for url, texto in enlaces:
            if url.startswith("http"):
                texto_limpio = re.sub(r"<[^>]+>", " ", texto).strip()
                resultado.append((url, texto_limpio))
        return resultado

    def _guess_mime(self, filename: str) -> str:
        ext = filename.lower().split(".")[-1]
        return {
            "pdf": "application/pdf",
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png",
            "xml": "application/xml",
        }.get(ext, "application/octet-stream")

    # ═══════════════════════════════════════════════════════════════════════
    # PREPARAR PAYLOAD MULTIMODAL PARA IA
    # ═══════════════════════════════════════════════════════════════════════

    # ── Una factura puede llegar de cuatro formas (jmd, 18-oct-2026): imagen adjunta, PDF
    # adjunto, dentro del cuerpo del correo o detrás de un enlace. Las cuatro acaban aquí
    # como imágenes o texto, porque es lo que todo modelo entiende (el PDF "nativo" solo lo
    # aceptan algunos de la nube; el modelo local lo rechaza).
    MAX_PAGINAS_PDF = 8          # una factura normal tiene 1-2; el tope evita catálogos
    MAX_DESCARGA_MB = 15
    MAX_ENLACES = 3

    @staticmethod
    def _pdf_a_imagenes(contenido: bytes, max_paginas: int = MAX_PAGINAS_PDF) -> list[str]:
        """Cada página del PDF a PNG en base64. Lista vacía si no se puede abrir."""
        try:
            import pymupdf
        except ImportError:  # pragma: no cover
            try:
                import fitz as pymupdf  # type: ignore
            except ImportError:
                logger.warning("PDF recibido pero no hay PyMuPDF: no se puede convertir")
                return []
        paginas: list[str] = []
        try:
            doc = pymupdf.open(stream=contenido, filetype="pdf")
        except Exception as e:  # raiz: PDF roto o cifrado al abrirlo con PyMuPDF -> sin paginas; se sigue sin el  # noqa: BLE001
            logger.warning("PDF ilegible: %s", e)
            return []
        try:
            for pagina in doc[:max_paginas]:
                # 200 ppp: suficiente para leer importes y CIF sin inflar la petición.
                pix = pagina.get_pixmap(dpi=200)
                paginas.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
        except Exception as e:  # raiz: pagina del PDF no convertible a imagen -> esa pagina se omite; las demas se leen  # noqa: BLE001
            logger.warning("Fallo convirtiendo página de PDF: %s", e)
        finally:
            doc.close()
        return paginas

    def _imagenes_del_cuerpo(self, email: EmailCompleto) -> list[tuple[str, str]]:
        """Imágenes incrustadas en el cuerpo (no adjuntas): las `cid:` que ya vienen entre
        los adjuntos del correo y las `data:` escritas en el propio HTML."""
        salida: list[tuple[str, str]] = []
        html = email.cuerpo_html or ""
        for cid in re.findall(r'src=["\']cid:([^"\']+)["\']', html, re.I):
            clave = cid.strip("<>").lower()
            for adj in email.adjuntos:
                nombre = (adj.get("filename") or "").lower()
                if clave and clave in nombre and str(adj.get("mime_type", "")).startswith("image/"):
                    salida.append((adj["mime_type"], base64.b64encode(adj["content"]).decode("ascii")))
                    break
        for mime, b64 in re.findall(r'src=["\']data:(image/[a-z+]+);base64,([^"\']+)["\']', html, re.I):
            salida.append((mime, b64.strip()))
        return salida

    def _descargar_enlaces(self, email: EmailCompleto) -> list[dict]:
        """Descarga lo que haya detrás de los enlaces del correo (muchos proveedores no
        adjuntan la factura: mandan un enlace). Solo http(s), solo PDF o imagen, con tope de
        tamaño y de número, y nunca direcciones internas de la red."""
        fuera: list[dict] = []
        vistos: set[str] = set()
        for url, texto in (email.enlaces or []):
            if len(fuera) >= self.MAX_ENLACES:
                break
            if not url.lower().startswith(("http://", "https://")) or url in vistos:
                continue
            vistos.add(url)
            if not re.search(r"(factura|invoice|descarg|download|document|recibo|\.pdf)", f"{url} {texto}", re.I):
                continue
            try:
                import ipaddress
                import socket
                from urllib.parse import urlparse
                host = urlparse(url).hostname or ""
                ip = ipaddress.ip_address(socket.gethostbyname(host))
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    logger.warning("Enlace a una dirección interna, no se descarga")
                    continue
                with httpx.Client(timeout=30, follow_redirects=True) as cli:
                    r = cli.get(url, headers={"User-Agent": "MakingSmiles Gestor IA"})
                r.raise_for_status()
                if len(r.content) > self.MAX_DESCARGA_MB * 1024 * 1024:
                    logger.warning("Enlace descartado por tamaño (%s MB)", len(r.content) // 1024 // 1024)
                    continue
                tipo = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
                if tipo not in ("application/pdf",) and not tipo.startswith("image/"):
                    continue
                fuera.append({"filename": url.rsplit("/", 1)[-1][:80] or "enlace",
                              "content": r.content, "mime_type": tipo, "origen": "enlace"})
            except Exception as e:  # raiz: enlace del correo no descargable o ilegible -> se omite el enlace; no tumba el correo  # noqa: BLE001
                logger.warning("No se pudo descargar un enlace del correo: %s", type(e).__name__)
        return fuera

    def _preparar_payload_multimodal(self, email: EmailCompleto) -> dict:
        """Prepara el payload completo para la IA multimodal."""
        
        # Texto base del email
        texto_email = f"""Remitente: {email.remitente}
Asunto: {email.asunto}
Fecha: {email.fecha.isoformat()}

CUERPO DEL EMAIL:
{email.cuerpo_texto[:10000]}"""

        # Adjuntos del correo + lo que haya detrás de sus enlaces
        archivos_ia = []
        for adj in list(email.adjuntos) + self._descargar_enlaces(email):
            if adj["mime_type"].startswith(("application/pdf", "image/")):
                import base64
                b64 = base64.b64encode(adj["content"]).decode("ascii")
                archivos_ia.append({
                    "filename": adj["filename"],
                    "mime_type": adj["mime_type"],
                    "base64": b64
                })

        # Enlaces de descarga directa
        enlaces_texto = "\n".join([f"- {url} (texto: {txt})" for url, txt in email.enlaces])

        # Construir mensaje para IA
        partes_usuario = [{"type": "text", "text": texto_email}]
        
        if archivos_ia:
            partes_usuario.append({"type": "text", "text": f"\nADJUNTOS ({len(archivos_ia)}):"})
            for arch in archivos_ia:
                partes_usuario.append({
                    "type": "text", 
                    "text": f"  - {arch['filename']} ({arch['mime_type']})"
                })
                # Para PDF/imagen, añadir como parte multimodal
                if arch["mime_type"] == "application/pdf":
                    # Cada página como imagen: así lo entiende cualquier modelo, también el
                    # local. Si no se puede abrir, se manda igual como fichero por si el
                    # proveedor de turno sabe leerlo.
                    paginas = self._pdf_a_imagenes(base64.b64decode(arch["base64"]))
                    if paginas:
                        for n, pagina in enumerate(paginas, 1):
                            partes_usuario.append({"type": "text", "text": f"    página {n} de {len(paginas)}:"})
                            partes_usuario.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{pagina}"}
                            })
                    else:
                        partes_usuario.append({
                            "type": "file",
                            "file": {
                                "filename": arch["filename"],
                                "file_data": arch["base64"],
                                "mime_type": arch["mime_type"]
                            }
                        })
                elif arch["mime_type"].startswith("image/"):
                    partes_usuario.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{arch['mime_type']};base64,{arch['base64']}"}
                    })

        incrustadas = self._imagenes_del_cuerpo(email)
        if incrustadas:
            partes_usuario.append({"type": "text", "text": f"\nIMÁGENES DENTRO DEL CUERPO ({len(incrustadas)}):"})
            for mime, b64 in incrustadas[:5]:
                partes_usuario.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        if enlaces_texto:
            partes_usuario.append({"type": "text", "text": f"\nENLACES DEL EMAIL:\n{enlaces_texto}"})

        # Few-shots
        few_shots_texto = self._construir_few_shots()

        return {
            "system_prompt": SYSTEM_PROMPT + "\n\n" + few_shots_texto + self._limites_ia(),
            "user_parts": partes_usuario,
            "config": self.config_ia
        }

    def _limites_ia(self) -> str:
        """Los límites que la clínica le escribe al Gestor, para el prompt REAL de facturas.

        Este es el prompt de producción: el que lee cada factura que entra por correo. Lo
        que la clínica escriba en Config › Agentes IA («verifica el CIF», «de más de 1000 €
        a revisión humana») tiene que llegar AQUÍ o no sirve de nada. Sin config valen los
        del catálogo.

        No revienta si falla: un límite que no se puede leer no debe impedir que la factura
        se procese — se queda sin el bloque y sigue."""
        try:
            from application.services.agente_service import AgenteService
            return AgenteService(self.session)._limites_centro(self.centro_id, "gestor")
        except Exception:  # raiz: no se pueden leer los limites del Gestor (config/BD) -> se sigue sin el bloque de limites  # noqa: BLE001
            logger.warning("No se pudieron leer los límites del Gestor; sigue sin ellos",
                           exc_info=True)
            return ""

    def _construir_few_shots(self) -> str:
        """Construye few-shots para el prompt."""
        shots = []
        for i, shot in enumerate(FEW_SHOTS[:5]):  # Máximo 5 few-shots
            shots.append(f"EJEMPLO {i+1} - {shot['descripcion']}:\n"
                        f"Email: {shot['email'][:500]}...\n"
                        f"Respuesta esperada: {json.dumps(shot['respuesta_esperada'], ensure_ascii=False)}")
        return "\n\n---\n\n".join(shots)

    # ═══════════════════════════════════════════════════════════════════════
    # LLAMADA A IA MULTIMODAL (OpenRouter: Gemini 2.5 Flash)
    # ═══════════════════════════════════════════════════════════════════════

    def _relevo_fallback_legacy(self, config: ModeloMultimodalConfig) -> Optional[dict]:
        """Reconstruye como relevo de `LLMClient` el fallback REAL que existía antes de la
        Task 1 (modelo_fallback/base_url_fallback/api_key_fallback/extra_body_fallback de
        `ModeloMultimodalConfig`, ver docstring de esos campos en ia_multimodal.py). Antes
        apuntaba a Ollama nativo vía `_pedir_a_ollama` (ya eliminado); ahora que
        `self.relevos` puede estar vacío en producción, sin esto se perdía sin sustituto
        ese fallback real (C2 de la revisión final de rama).

        C2a (re-revisión, ronda 2): la señal de activación REAL, verificada contra el código
        original (commit 40e5556, antes de toda esta rama), es
        `modelo_fallback and modelo_fallback != modelo` — NO exigir `base_url_fallback` no
        vacío. El código viejo usaba `base_url_fallback or config.base_url`: "vacío" en ese
        campo significaba "el fallback usa la base_url del PRIMARIO con el modelo_fallback",
        no "sin fallback" (así lo confirma el propio docstring del campo en
        ia_multimodal.py: "vacío = la del principal"). Mi primer intento exigía
        base_url_fallback no vacío y perdía ese caso real; lo detecté porque rompía
        `test_llamar_ia_multimodal_usa_llmclient_con_relevos` y entonces ajusté el CÓDIGO
        para que el test pasara en vez de corregir la lógica — error de proceso señalado por
        el re-revisor, corregido aquí."""
        if not config.modelo_fallback or config.modelo_fallback == config.modelo:
            return None
        return {
            "nombre": "fallback_legacy",
            "base_url": (config.base_url_fallback or config.base_url),
            "api_key": (config.api_key_fallback or self.openrouter_key or ""),
            "model": config.modelo_fallback,
            # LLMClient._candidatos NO soporta `extra_body` por candidato (solo
            # `reasoning_effort`, ver llm_client.py). Si extra_body_fallback trae algo
            # distinto de `enable_thinking`/reasoning, se pierde — limitación documentada,
            # no inventada: no hay forma de pasarlo a día de hoy sin tocar LLMClient
            # (fuera de alcance de este fix).
            "reasoning_effort": (
                "none" if (config.extra_body_fallback or {})
                .get("chat_template_kwargs", {}).get("enable_thinking") is False
                else None
            ),
        }

    async def _llamar_ia_multimodal(self, payload: dict) -> Optional[dict]:
        """Llama a la IA multimodal vía `LLMClient` (infraestructura): el primario de la
        integración `gestor_multimodal` + su cadena de `relevos` (Plan B), con el mismo
        contrato de fallo que ya tenía `LLMClient.chat` — si ningún candidato responde,
        se captura `LLMError` y se devuelve `None`, igual que el fallback propio de antes.

        C2 (revisión final de rama): el fallback real anterior (modelo_fallback/
        base_url_fallback/api_key_fallback de la integración) se añade SIEMPRE como relevo
        adicional, ANTES de los `self.relevos` configurados — así sigue disponible tras el
        merge, no solo el relevo nuevo (hoy vacío en producción)."""
        if not self.openrouter_key:
            logger.error("OpenRouter API key no configurada")
            return None

        config = payload["config"]
        relevo_legacy = self._relevo_fallback_legacy(config)
        relevos = ([relevo_legacy] if relevo_legacy else []) + list(self.relevos)
        cfg = {
            "base_url": config.base_url,
            "api_key": self.openrouter_key,
            "model": config.modelo,
            "relevos": relevos,
        }

        messages = [
            {"role": "system", "content": payload["system_prompt"]},
            {"role": "user", "content": payload["user_parts"]}
        ]

        try:
            mensaje = await asyncio.to_thread(
                LLMClient(cfg).chat, messages, temperature=0.0, max_tokens=config.max_tokens
            )
        except LLMError as e:
            logger.warning("Ningún proveedor LLM respondió para gestor_multimodal: %s", e)
            return None

        contenido = (mensaje or {}).get("content") or ""
        if not contenido:
            logger.warning("IA devolvió respuesta vacía")
            return None
        try:
            i, j = contenido.find("{"), contenido.rfind("}")
            return json.loads(contenido if i == -1 else contenido[i:j + 1])
        except json.JSONDecodeError as e:
            logger.error("Error parseando JSON de IA: %s", e)
            return None

    @staticmethod
    def _imagen_para_ollama(b64: str) -> Optional[str]:
        """Ollama solo carga JPEG/PNG: un GIF, SVG o icono del cuerpo del correo tumbaba la
        petición entera con 400 "Failed to load image" (23-oct-2026). PNG y JPEG pasan tal
        cual; el resto se convierte a JPEG, y lo que no se puede decodificar (SVG) se omite."""
        try:
            crudo = base64.b64decode(b64)
        except Exception:  # raiz: base64 de imagen corrupto -> imagen omitida para Ollama, no rompe la peticion  # noqa: BLE001
            return None
        if crudo[:8] == b"\x89PNG\r\n\x1a\n" or crudo[:3] == b"\xff\xd8\xff":
            return b64
        try:
            from PIL import Image
            with Image.open(io.BytesIO(crudo)) as im:
                salida = io.BytesIO()
                im.convert("RGB").save(salida, format="JPEG", quality=90)
            return base64.b64encode(salida.getvalue()).decode("ascii")
        except Exception:  # raiz: imagen no decodificable (SVG/formato raro) -> se omite; no tumba el correo  # noqa: BLE001
            logger.info("Imagen del correo omitida para Ollama: formato no legible")
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # PROCESAR CLASIFICACIÓN Y REGISTRAR EN BD
    # ═══════════════════════════════════════════════════════════════════════

    async def _procesar_clasificacion(
        self, 
        email: EmailCompleto, 
        datos: GastoIAResponse
    ) -> ProcesamientoResultado:
        """Procesa según la clasificación de la IA."""
        
        if datos.accion == "gasto":
            return await self._registrar_gasto(email, datos)
        elif datos.accion == "duplicado":
            return await self._manejar_duplicado(email, datos)
        elif datos.accion == "incidencia":
            return await self._manejar_incidencia(email, datos)
        elif datos.accion == "descartado":
            return await self._manejar_descartado(email, datos)
        else:
            return ProcesamientoResultado(ok=False, accion="error", error=f"Acción desconocida: {datos.accion}")

    async def _registrar_gasto(self, email: EmailCompleto, datos: GastoIAResponse) -> ProcesamientoResultado:
        """Registra o actualiza gasto en BD + sube PDF a Drive."""
        
        # 1. Buscar duplicado (CIF + nº factura + total)
        duplicado = self._buscar_duplicado(datos)
        if duplicado:
            return await self._manejar_duplicado(email, datos, duplicado)

        # 2. Subir PDF a Drive
        drive_url = await self._subir_pdf_drive(email, datos)
        
        # 3. Crear/actualizar proveedor
        proveedor_id = self._upsert_proveedor(datos)
        
        # 4. Crear gasto
        gasto = Gasto(
            centro_id=self.centro_id,
            proveedor_id=proveedor_id,
            proveedor_extraido=datos.proveedor_nombre,
            cif_emisor=datos.cif_emisor,
            numero_factura=datos.numero_factura,
            fecha=datos.fecha_emision,
            concepto=datos.concepto,
            base_imponible=Decimal(str(datos.base_imponible or 0)),
            iva_pct=Decimal(str(datos.iva_pct or 0)),
            # `Gasto` NO tiene campo `irpf`: el real es `retencion`. Con `irpf=` el valor se
            # perdía en silencio (sin error, sin log) y la retención se guardaba a 0.
            retencion=Decimal(str(datos.irpf_importe or 0)),
            suplido=Decimal(str(datos.suplido or 0)),
            total=Decimal(str(datos.total or 0)),
            divisa=datos.divisa,
            tipo_documento=datos.tipo_documento,
            forma_pago=self._determinar_forma_pago(datos),
            estado="pendiente",
            archivo_pdf_url=drive_url,
            gmail_message_id=email.message_id,
            categoria=datos.categoria_contable,
        )
        
        self.session.add(gasto)
        self.session.commit()
        self.session.refresh(gasto)
        
        # 5. Mover email a "Facturas/Facturas Procesadas"
        await self._mover_email_procesado(email.uid)
        
        # 6. Emitir WebSocket (se implementará en Fase 4)
        # await self._emitir_websocket_gasto_nuevo(gasto)
        
        return ProcesamientoResultado(
            ok=True, accion="gasto", gasto_id=gasto.id, 
            proveedor_id=proveedor_id, drive_url=drive_url,
            detalles=f"Gasto registrado: {datos.proveedor_nombre} - {datos.total}€"
        )

    async def _manejar_duplicado(self, email: EmailCompleto, datos: GastoIAResponse, duplicado: Optional[Gasto] = None) -> ProcesamientoResultado:
        """Maneja factura duplicada: mueve email, no registra."""
        await self._mover_email_procesado(email.uid)
        return ProcesamientoResultado(
            ok=True, accion="duplicado",
            detalles=f"Duplicado detectado: {datos.numero_factura} - {datos.total}€"
        )

    async def _manejar_incidencia(self, email: EmailCompleto, datos: GastoIAResponse) -> ProcesamientoResultado:
        """Mueve a Incidencias para revisión humana."""
        await self._mover_email_incidencias(email.uid)
        return ProcesamientoResultado(
            ok=True, accion="incidencia",
            detalles=f"Incidencia: {datos.motivo_descarte}"
        )

    async def _manejar_descartado(self, email: EmailCompleto, datos: GastoIAResponse) -> ProcesamientoResultado:
        """Mueve a Desechados (no es gasto)."""
        await self._mover_email_desechados(email.uid)
        return ProcesamientoResultado(
            ok=True, accion="descartado",
            detalles=f"Descartado: {datos.motivo_descarte}"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # HELPERS: DEDUPLICACIÓN, PROVEEDOR, DRIVE, GMAIL
    # ═══════════════════════════════════════════════════════════════════════

    def _buscar_duplicado(self, datos: GastoIAResponse) -> Optional[Gasto]:
        """Busca duplicado por CIF + nº factura (fuerte) o nº factura + total (fallback)."""
        if datos.cif_emisor and datos.numero_factura:
            g = self.session.exec(select(Gasto).where(
                Gasto.centro_id == self.centro_id,
                Gasto.cif_emisor == datos.cif_emisor,
                Gasto.numero_factura == datos.numero_factura
            )).first()
            if g:
                return g
        
        if datos.numero_factura and datos.total:
            g = self.session.exec(select(Gasto).where(
                Gasto.centro_id == self.centro_id,
                Gasto.numero_factura == datos.numero_factura,
                Gasto.total == Decimal(str(datos.total))
            )).first()
            if g:
                return g
        
        return None

    def _upsert_proveedor(self, datos: GastoIAResponse) -> Optional[int]:
        """Crea o actualiza proveedor por CIF. None si la factura no trae CIF válido."""
        if not datos.cif_emisor:
            # Identidad = CIF (regla dura del área): sin identificación fiscal NO se crea
            # proveedor. Antes se daba de alta uno llamado "SIN CIF", saltándose el resolver
            # único y generando duplicados sin identidad. La factura conserva el nombre en
            # texto (`proveedor_extraido`), que es el comportamiento querido.
            return None
        
        # Buscar por CIF
        prov = self.session.exec(select(Proveedor).where(
            Proveedor.centro_id == self.centro_id,
            Proveedor.cif == datos.cif_emisor
        )).first()
        
        if prov:
            # Actualizar datos si faltan
            if datos.proveedor_nombre and prov.nombre == prov.cif:
                prov.nombre = datos.proveedor_nombre
            if datos.direccion_proveedor and not prov.direccion:
                prov.direccion = datos.direccion_proveedor
            if datos.telefono_proveedor and not prov.telefono:
                prov.telefono = datos.telefono_proveedor
            if datos.email_proveedor and not prov.email_contacto:
                prov.email_contacto = datos.email_proveedor
            if datos.categoria_contable and not prov.categoria_defecto:
                prov.categoria_defecto = datos.categoria_contable
            self.session.add(prov)
        else:
            prov = Proveedor(
                centro_id=self.centro_id,
                nombre=datos.proveedor_nombre or datos.cif_emisor,
                cif=datos.cif_emisor,
                direccion=datos.direccion_proveedor,
                telefono=datos.telefono_proveedor,
                email_contacto=datos.email_proveedor,
                categoria_defecto=datos.categoria_contable,
            )
            self.session.add(prov)
        
        self.session.commit()
        self.session.refresh(prov)
        return prov.id

    async def _subir_pdf_drive(self, email: EmailCompleto, datos: GastoIAResponse) -> Optional[str]:
        """Sube PDF a Drive. Si no hay adjunto PDF, genera uno con los datos."""
        # Buscar adjunto PDF
        pdf_content = None
        pdf_filename = None
        
        for adj in email.adjuntos:
            if adj["mime_type"] == "application/pdf":
                pdf_content = adj["content"]
                pdf_filename = adj["filename"]
                break
        
        if not pdf_content:
            # Generar PDF con los datos extraídos
            pdf_content = self._generar_pdf_datos(datos)
            pdf_filename = f"{datos.fecha_emision}_{datos.proveedor_nombre}_{datos.numero_factura}.pdf"
        
        if not pdf_content:
            return None
        
        if not self.drive_config or not drive_client.configurado(self.drive_config):
            # Fallback local
            return self._guardar_pdf_local(pdf_content, pdf_filename)
        
        # Subir a Drive
        try:
            folder_id = self.drive_config.get("carpeta_facturas") or self.drive_config.get("folder_id")
            result = drive_client.subir(
                self.drive_config,
                filename=pdf_filename,
                content=pdf_content,
                mime="application/pdf",
                folder_id=folder_id
            )
            return result.get("url") or f"https://drive.google.com/file/d/{result['id']}/view"
        except Exception as e:  # raiz: subida a Drive falla (red/credenciales) -> fallback a guardar el PDF en local
            logger.error(f"Error subiendo a Drive: {e}")
            return self._guardar_pdf_local(pdf_content, pdf_filename)

    def _guardar_pdf_local(self, content: bytes, filename: str) -> str:
        """Guarda PDF en /media/facturas/ local."""
        from pathlib import Path
        # Ruta relativa al paquete backend/, NO "/media/facturas" (raíz del contenedor):
        # el resto del proyecto resuelve así (cf. gestoria_router extracto_descargar).
        media_dir = Path(__file__).resolve().parents[2] / "media" / "facturas"
        media_dir.mkdir(parents=True, exist_ok=True)
        filepath = media_dir / filename
        filepath.write_bytes(content)
        return f"/media/facturas/{filename}"   # URL pública servida por el backend

    def _generar_pdf_datos(self, datos: GastoIAResponse) -> bytes:
        """Genera PDF simple con los datos del gasto."""
        from fpdf import FPDF
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "FACTURA GENERADA POR IA", ln=True, align="C")
        pdf.ln(5)
        
        pdf.set_font("Helvetica", "", 10)
        campos = [
            ("Proveedor", datos.proveedor_nombre),
            ("CIF/NIF", datos.cif_emisor),
            ("Nº Factura", datos.numero_factura),
            ("Fecha", str(datos.fecha_emision)),
            ("Base Imponible", f"{datos.base_imponible:.2f} {datos.divisa}"),
            ("IVA", f"{datos.iva_pct}%"),
            ("IRPF", f"{datos.irpf_importe:.2f} {datos.divisa}"),
            ("Suplido", f"{datos.suplido:.2f} {datos.divisa}"),
            ("TOTAL", f"{datos.total:.2f} {datos.divisa}"),
            ("Concepto", datos.concepto or ""),
            ("Categoría", datos.categoria_contable or ""),
            ("Destinatario", datos.destinatario or ""),
            ("Origen dato", datos.origen_dato),
            ("Notas IA", datos.notas),
        ]
        
        for label, value in campos:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(50, 6, f"{label}:", ln=False)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 6, str(value or "-"), ln=True)
        
        return pdf.output(dest="S").encode("latin-1")

    def _determinar_forma_pago(self, datos: GastoIAResponse) -> str:
        """Determina forma de pago canónica."""
        if datos.destinatario and "MANZANEDO" in datos.destinatario.upper():
            return "Tarjeta Deb. Juan A. Manzanedo"
        # Por defecto transferencia para facturas normales
        return "Transferencia"

    # ═══════════════════════════════════════════════════════════════════════
    # MOVER EMAIL EN GMAIL
    # ═══════════════════════════════════════════════════════════════════════

    async def _mover_email_procesado(self, uid: str) -> bool:
        """Mueve email a 'Facturas/Facturas Procesadas'."""
        return await self._mover_email(uid, ETIQUETA_PROCESADAS)

    async def _mover_email_incidencias(self, uid: str) -> bool:
        """Mueve email a 'Facturas/Incidencias'."""
        return await self._mover_email(uid, ETIQUETA_INCIDENCIAS)

    async def _mover_email_desechados(self, uid: str) -> bool:
        """Mueve el correo a la papelera. "Facturas/Desechados" no es una carpeta real del
        buzón (verificado 2026-08-09); lo no facturable va a la papelera, igual que en
        `intake_service`."""
        return await self._mover_email(uid, CARPETA_PAPELERA)

    async def _mover_email(self, uid: str, destino: str) -> bool:
        """Mueve email via IMAP.

        SEGURIDAD: mover correos en el buzón real es una acción externa difícil de
        revertir, así que va GUARDADA tras INTAKE_MOVER_GMAIL=1 (default OFF), la misma
        salvaguarda que usa `intake_service.mover_etiqueta`. Con el flag apagado se
        procesa y se registra en BD (reversible) pero NO se toca Gmail.
        """
        if os.environ.get("INTAKE_MOVER_GMAIL") != "1":
            logger.info("Movimiento a %s omitido: INTAKE_MOVER_GMAIL no está activo", destino)
            return False
        if not self.imap_config or not uid:
            return False
        try:
            movidos = gmail_imap.mover(self.imap_config, "INBOX", [uid], destino)
            return movidos > 0
        except Exception as e:  # raiz: mover el correo en IMAP falla -> False; lo ya procesado se mantiene
            logger.error(f"Error moviendo email a {destino}: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════════
# FUNCIÓN DE ENTRADA PARA BACKGROUND TASK
# ═══════════════════════════════════════════════════════════════════════

async def procesar_email_webhook(centro_id: int, message_id: str) -> ProcesamientoResultado:
    """Función de entrada para background task (FastAPI BackgroundTasks)."""
    session = next(get_session())
    try:
        processor = GmailAIProcessor(session, centro_id)
        return await processor.procesar_webhook(message_id)
    finally:
        session.close()
