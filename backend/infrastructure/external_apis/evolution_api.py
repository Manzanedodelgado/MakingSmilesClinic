"""Cliente Evolution API para WhatsApp (infraestructura).

Port del evolution-api.service.ts de la .37 a Python (httpx). Solo I/O: habla con
una instancia de Evolution API. La config (url, api_key, instance) NO se hardcodea:
llega como dict desde `integraciones` (tipo='whatsapp') de cada centro → multi-tenant.

La decisión de qué hacer con cada mensaje (dedup, intents, IA) vive en el dominio.
"""
from typing import Any, Optional

import httpx

TIMEOUT = 20.0


class EvolutionError(RuntimeError):
    """Fallo al hablar con Evolution API.

    `numero_invalido` = Evolution respondió 400 porque el número no está en WhatsApp
    o no es válido (caso de negocio, NO error del servidor)."""

    def __init__(self, mensaje: str, *, status_code: Optional[int] = None,
                 body: Optional[str] = None, numero_invalido: bool = False):
        super().__init__(mensaje)
        self.status_code = status_code
        self.body = body
        self.numero_invalido = numero_invalido


def _fallo(prefijo: str, e: httpx.HTTPError) -> "EvolutionError":
    """Construye un EvolutionError con el estado/cuerpo de la respuesta, marcando el caso
    'número no está en WhatsApp' (400 con exists:false) para que la API lo trate como 4xx."""
    resp = getattr(e, "response", None)
    status = resp.status_code if resp is not None else None
    body = (resp.text or "")[:500] if resp is not None else None
    numero_invalido = bool(status == 400 and body and '"exists":false' in body.replace(" ", ""))
    return EvolutionError(f"{prefijo} falló: {e}", status_code=status, body=body,
                          numero_invalido=numero_invalido)


class EvolutionClient:
    """Una instancia de Evolution para UN centro. Se crea con su config."""

    def __init__(self, config: dict):
        # Claves de la pantalla de config (CanalesIA): url_api / instancia / api_key.
        # Se aceptan alias (url / instance) por compatibilidad.
        self.url = (config.get("url_api") or config.get("url") or "").rstrip("/")
        self.api_key = config.get("api_key") or ""
        self.instance = config.get("instancia") or config.get("instance") or ""
        if not self.url or not self.api_key or not self.instance:
            raise EvolutionError("Evolution API no configurada (faltan url_api/api_key/instancia)")

    # ── helpers ───────────────────────────────────────────────────────────────
    @property
    def _headers(self) -> dict:
        return {"apikey": self.api_key, "Content-Type": "application/json"}

    def _post(self, path: str, payload: dict) -> dict:
        try:
            r = httpx.post(f"{self.url}{path}", json=payload, headers=self._headers, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json() if r.content else {}
        except httpx.HTTPError as e:
            raise _fallo(f"POST {path}", e) from e

    def _get(self, path: str) -> dict:
        try:
            r = httpx.get(f"{self.url}{path}", headers=self._headers, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json() if r.content else {}
        except httpx.HTTPError as e:
            raise _fallo(f"GET {path}", e) from e

    def _delete(self, path: str, payload: dict) -> dict:
        try:
            r = httpx.request("DELETE", f"{self.url}{path}", json=payload, headers=self._headers, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json() if r.content else {}
        except httpx.HTTPError as e:
            raise _fallo(f"DELETE {path}", e) from e

    # ── estado / conexión ─────────────────────────────────────────────────────
    def connection_state(self) -> dict:
        """Estado de la instancia: {instance: {state: 'open'|'connecting'|'close'}}."""
        return self._get(f"/instance/connectionState/{self.instance}")

    def get_qr(self) -> dict:
        """Devuelve el QR para vincular (base64 en `base64`/`code`) si no está conectada."""
        return self._get(f"/instance/connect/{self.instance}")

    def restart_instance(self) -> dict:
        """Reinicia la instancia DENTRO de Evolution (sin tocar el contenedor). No siempre
        basta si el socket de Baileys quedó zombi con el estado cacheado en 'open' — en ese
        caso hace falta reiniciar el contenedor (ver infrastructure/docker_client.py)."""
        return self._post(f"/instance/restart/{self.instance}", {})

    def logout(self) -> dict:
        """DESVINCULA el WhatsApp actual de la instancia (cierra la sesión de Baileys) SIN
        borrar la instancia ni su config/webhook. Tras esto, get_qr() emite un QR nuevo para
        enlazar OTRO teléfono. Es el paso previo a re-vincular por QR."""
        return self._delete(f"/instance/logout/{self.instance}", {})

    def fetch_instance(self) -> dict:
        """Datos de la instancia, incluido el número/propietario conectado. Evolution v2 devuelve
        una lista; se filtra por instanceName. Claves útiles: ownerJid / number / profileName."""
        data = self._get(f"/instance/fetchInstances?instanceName={self.instance}")
        item = data[0] if isinstance(data, list) and data else (data or {})
        inst = item.get("instance") if isinstance(item, dict) and "instance" in item else item
        return inst or {}

    # ── webhook (recepción de mensajes) ────────────────────────────────────────
    def find_webhook(self) -> dict:
        """Webhook configurado en Evolution para esta instancia (url, events, enabled)."""
        return self._get(f"/webhook/find/{self.instance}")

    def set_webhook(self, url: str, events: list[str], enabled: bool = True) -> dict:
        """Registra/actualiza el webhook entrante (formato anidado v2)."""
        payload = {"webhook": {"enabled": enabled, "url": url,
                               "byEvents": False, "base64": False, "events": events}}
        return self._post(f"/webhook/set/{self.instance}", payload)

    # ── envío ─────────────────────────────────────────────────────────────────
    def send_text(self, number: str, text: str, quoted_message_id: Optional[str] = None,
                  delay: int = 1200) -> dict:
        payload: dict[str, Any] = {"number": number, "text": text, "delay": delay}
        if quoted_message_id:
            payload["quoted"] = {"key": {"id": quoted_message_id}}
        return self._post(f"/message/sendText/{self.instance}", payload)

    def send_media(self, number: str, media: str, media_type: str = "image",
                   mimetype: Optional[str] = None, filename: Optional[str] = None,
                   caption: Optional[str] = None) -> dict:
        payload: dict[str, Any] = {"number": number, "mediatype": media_type, "media": media}
        if mimetype:
            payload["mimetype"] = mimetype
        if filename:
            payload["fileName"] = filename
        if caption:
            payload["caption"] = caption
        return self._post(f"/message/sendMedia/{self.instance}", payload)

    def send_poll(self, number: str, name: str, values: list[str],
                  selectable_count: int = 1) -> dict:
        payload = {"number": number, "name": name,
                   "selectableCount": selectable_count, "values": values}
        return self._post(f"/message/sendPoll/{self.instance}", payload)

    def send_presence(self, number: str, presence: str = "composing", delay: int = 1200) -> dict:
        payload = {"number": number, "presence": presence, "delay": delay}
        return self._post(f"/chat/sendPresence/{self.instance}", payload)

    # ── editar / borrar (solo mensajes NUESTROS, antes de que el paciente los lea) ─────────────
    def delete_message_for_everyone(self, remote_jid: str, message_id: str) -> dict:
        """Borra un mensaje saliente para ambos (DTO real de Evolution: DeleteMessage —
        id/fromMe/remoteJid). `fromMe` siempre True: solo borramos lo que enviamos nosotros."""
        payload = {"id": message_id, "fromMe": True, "remoteJid": remote_jid}
        return self._delete(f"/chat/deleteMessageForEveryone/{self.instance}", payload)

    def update_message(self, number: str, remote_jid: str, message_id: str, text: str) -> dict:
        """Edita el texto de un mensaje saliente ya enviado (DTO real: UpdateMessageDto —
        number + key{remoteJid,fromMe,id} + text)."""
        payload = {"number": number, "key": {"remoteJid": remote_jid, "fromMe": True, "id": message_id}, "text": text}
        return self._post(f"/chat/updateMessage/{self.instance}", payload)

    def get_base64_from_media(self, message: dict) -> dict:
        """Descarga el media de un mensaje recibido en base64."""
        return self._post(f"/chat/getBase64FromMediaMessage/{self.instance}", {"message": message})

    # ── historial (sincronización de chats/mensajes ya existentes) ─────────────
    def find_chats(self) -> list:
        """Lista los chats conocidos por la instancia. Cada item: {remoteJid, pushName,
        lastMessage, unreadCount, updatedAt, ...}. Incluye grupos (@g.us) y estados."""
        data = self._post(f"/chat/findChats/{self.instance}", {})
        if isinstance(data, list):
            return data
        return (data.get("chats") if isinstance(data, dict) else None) or []

    def find_messages(self, remote_jid: str) -> list:
        """Mensajes de UN chat (por remoteJid). Devuelve la lista de `records` cruda de
        Evolution: cada uno con key{id,fromMe,remoteJid}, message{...}, messageTimestamp."""
        data = self._post(f"/chat/findMessages/{self.instance}",
                          {"where": {"key": {"remoteJid": remote_jid}}})
        if isinstance(data, list):
            return data
        msgs = (data or {}).get("messages") or {}
        if isinstance(msgs, dict):
            return msgs.get("records") or []
        return msgs if isinstance(msgs, list) else []


def test_connection(config: dict) -> dict:
    """Prueba la config sin lanzar: devuelve {ok, estado?, error?}."""
    try:
        cli = EvolutionClient(config)
        state = cli.connection_state()
        estado = (state.get("instance") or {}).get("state") or state.get("state")
        return {"ok": True, "estado": estado}
    except EvolutionError as e:
        return {"ok": False, "error": str(e)}
