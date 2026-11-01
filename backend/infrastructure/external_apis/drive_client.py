"""Subida de ficheros a Google Drive (infraestructura).

Config en integraciones (tipo='google_drive'):
  - Service account:  {sa_b64 (JSON del SA en base64), folder_id}
  - OAuth (alt.):     {client_id, client_secret, refresh_token, folder_id}
  - API key (SOLO LECTURA): {api_key, folder_id} → para carpetas compartidas por enlace.
Obtiene un access token y sube por la Drive REST API (multipart). Si no hay
credenciales, el servicio que lo llama cae a almacenamiento local.

ESCRITURA (subir/mover/crear) requiere OAuth o service account → `configurado()`.
LECTURA (listar/descargar) admite además una API key sobre carpetas compartidas
por enlace → `configurado_lectura()`. Una API key NO puede escribir ni leer
ficheros privados (la carpeta debe estar compartida "cualquiera con el enlace").
"""
import base64
import json
import time
from typing import Optional

import httpx
import jwt

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = ("https://www.googleapis.com/upload/drive/v3/files"
              "?uploadType=multipart&supportsAllDrives=true&fields=id,webViewLink")
SCOPE = "https://www.googleapis.com/auth/drive"


class DriveError(RuntimeError):
    pass


def _tiene_token(cfg: Optional[dict]) -> bool:
    """Hay credenciales capaces de obtener un access token bearer (OAuth o SA)."""
    if not cfg:
        return False
    return bool(cfg.get("sa_b64") or (cfg.get("refresh_token") and cfg.get("client_id")))


def configurado(cfg: Optional[dict]) -> bool:
    """ESCRITURA: subir/mover/crear carpetas requiere bearer (OAuth o service account)."""
    return _tiene_token(cfg)


def configurado_lectura(cfg: Optional[dict]) -> bool:
    """LECTURA: además del bearer, vale una API key (carpeta compartida por enlace)."""
    return _tiene_token(cfg) or bool((cfg or {}).get("api_key"))


def _read_auth(cfg: dict) -> tuple[dict, dict]:
    """(params_extra, headers) para peticiones de LECTURA. Prioriza bearer; si solo
    hay api_key, autentica con ?key=… y sin cabecera Authorization."""
    if _tiene_token(cfg):
        return {}, {"Authorization": f"Bearer {_access_token(cfg)}"}
    ak = (cfg or {}).get("api_key")
    if ak:
        return {"key": ak}, {}
    # sin credenciales: deja que _access_token lance un DriveError claro.
    return {}, {"Authorization": f"Bearer {_access_token(cfg)}"}


def _sa(cfg: dict) -> Optional[dict]:
    if cfg.get("sa_b64"):
        return json.loads(base64.b64decode(cfg["sa_b64"]))
    return None


# Caché de access tokens (módulo): evita pedir un token nuevo en CADA llamada a Drive — antes
# eran 4-5 refresh por ficha y, si Google fallaba uno, esa columna salía vacía. Token válido ~1h.
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def _token_cache_key(cfg: dict) -> str:
    return cfg.get("refresh_token") or cfg.get("sa_b64") or cfg.get("subject", "") or "default"


def _access_token(cfg: dict) -> str:
    key = _token_cache_key(cfg)
    now = time.time()
    cached = _TOKEN_CACHE.get(key)
    if cached and cached[1] - 120 > now:   # reutiliza si quedan >2 min de validez
        return cached[0]
    sa = _sa(cfg)
    if sa:  # service account → JWT bearer
        iat = int(now)
        claims = {"iss": sa["client_email"], "scope": SCOPE, "aud": TOKEN_URL,
                  "iat": iat, "exp": iat + 3600}
        # Delegación de dominio: suplanta a un usuario real (con cuota) para subir contenido.
        if cfg.get("subject"):
            claims["sub"] = cfg["subject"]
        assertion = jwt.encode(claims, sa["private_key"], algorithm="RS256")
        r = httpx.post(TOKEN_URL, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}, timeout=20)
    else:  # OAuth refresh token
        r = httpx.post(TOKEN_URL, data={
            "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
            "refresh_token": cfg["refresh_token"], "grant_type": "refresh_token"}, timeout=20)
    if r.status_code != 200:
        raise DriveError(f"Auth Drive falló: {r.status_code} {r.text[:200]}")
    data = r.json()
    token = data["access_token"]
    _TOKEN_CACHE[key] = (token, now + float(data.get("expires_in", 3600)))
    return token


def subir(cfg: dict, *, filename: str, content: bytes, mime: str = "application/pdf",
          folder_id: Optional[str] = None) -> dict:
    token = _access_token(cfg)
    meta = {"name": filename}
    destino = folder_id or cfg.get("folder_id")
    if destino:
        meta["parents"] = [destino]
    boundary = "msf-drive-boundary"
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--".encode()
    r = httpx.post(UPLOAD_URL, content=body, timeout=60, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/related; boundary={boundary}"})
    if r.status_code not in (200, 201):
        raise DriveError(f"Subida Drive falló: {r.status_code} {r.text[:200]}")
    d = r.json()
    return {"id": d.get("id"), "url": d.get("webViewLink")}


def buscar_o_crear_carpeta(cfg: dict, nombre: str, parent_id: str) -> Optional[str]:
    """Devuelve el id de la subcarpeta `nombre` dentro de `parent_id`; la crea si no existe.
    Devuelve None si algo falla (el llamador debe caer a la carpeta padre)."""
    try:
        token = _access_token(cfg)
        safe = nombre.replace("'", "")
        q = (f"'{parent_id}' in parents and name = '{safe}' "
             "and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
        r = httpx.get("https://www.googleapis.com/drive/v3/files", params={
            "q": q, "fields": "files(id)", "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true"}, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        files = r.json().get("files", []) if r.status_code == 200 else []
        if files:
            return files[0]["id"]
        meta = {"name": nombre, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
        r2 = httpx.post("https://www.googleapis.com/drive/v3/files",
                        params={"supportsAllDrives": "true", "fields": "id"}, json=meta,
                        headers={"Authorization": f"Bearer {token}"}, timeout=20)
        return r2.json().get("id") if r2.status_code in (200, 201) else None
    except Exception:  # noqa: BLE001
        return None


def buscar_subcarpeta_prefijo(cfg: dict, parent_id: str, prefijo: str) -> Optional[str]:
    """Id de la subcarpeta de `parent_id` cuyo nombre EMPIEZA por `prefijo`.
    Drive no soporta 'starts with' en la query, así que filtra con `contains` y confirma
    en cliente. None si no hay credenciales o no se encuentra."""
    try:
        extra, headers = _read_auth(cfg)
        safe = prefijo.replace("'", "").strip()
        q = (f"'{parent_id}' in parents and name contains '{safe}' "
             "and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
        r = httpx.get("https://www.googleapis.com/drive/v3/files", params={
            "q": q, "fields": "files(id,name)", "pageSize": 20, "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true", **extra}, headers=headers, timeout=20)
        if r.status_code != 200:
            return None
        for f in r.json().get("files", []):
            if (f.get("name") or "").startswith(prefijo):
                return f["id"]
        return None
    except Exception:  # noqa: BLE001
        return None


def listar_imagenes(cfg: dict, folder_id: str) -> list[dict]:
    """Imágenes (image/* o PDF) directas de `folder_id`, ordenadas por fecha desc.
    Lista vacía si falla o no hay credenciales."""
    try:
        extra, headers = _read_auth(cfg)
        q = (f"'{folder_id}' in parents and trashed = false "
             "and (mimeType contains 'image/' or mimeType = 'application/pdf')")
        r = httpx.get("https://www.googleapis.com/drive/v3/files", params={
            "q": q, "orderBy": "createdTime desc", "pageSize": 200,
            "fields": "files(id,name,mimeType,size,createdTime)",
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true", **extra},
            headers=headers, timeout=30)
        return r.json().get("files", []) if r.status_code == 200 else []
    except Exception:  # noqa: BLE001
        return []


def listar_subcarpetas(cfg: dict, folder_id: str) -> list[dict]:
    """Subcarpetas directas de `folder_id` (id, name). Lista vacía si falla."""
    try:
        extra, headers = _read_auth(cfg)
        q = (f"'{folder_id}' in parents and trashed = false "
             "and mimeType = 'application/vnd.google-apps.folder'")
        r = httpx.get("https://www.googleapis.com/drive/v3/files", params={
            "q": q, "fields": "files(id,name)", "pageSize": 50,
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true", **extra},
            headers=headers, timeout=20)
        return r.json().get("files", []) if r.status_code == 200 else []
    except Exception:  # noqa: BLE001
        return []


def descargar_media(cfg: dict, file_id: str) -> Optional[tuple[bytes, str]]:
    """(bytes, content-type) del fichero completo (alt=media). None si falla."""
    try:
        extra, headers = _read_auth(cfg)
        r = httpx.get(f"https://www.googleapis.com/drive/v3/files/{file_id}",
                      params={"alt": "media", "supportsAllDrives": "true", **extra},
                      headers=headers, timeout=60)
        if r.status_code != 200:
            return None
        return r.content, r.headers.get("Content-Type", "application/octet-stream")
    except Exception:  # noqa: BLE001
        return None


def thumbnail(cfg: dict, file_id: str, size: int = 400) -> Optional[tuple[bytes, str]]:
    """(bytes, content-type) de la miniatura de Drive a `size` px de lado mayor.
    Cae a `descargar_media` si el fichero no tuviera thumbnailLink."""
    try:
        # En modo API key usamos el endpoint público de miniatura de Drive (sirve
        # ficheros "cualquiera con el enlace" sin cabecera, ~50 KB en vez de la imagen
        # completa). Si fallara, caemos a la imagen completa por ?key=.
        if not _tiene_token(cfg):
            t = httpx.get(f"https://drive.google.com/thumbnail?id={file_id}&sz=s{size}",
                          timeout=30, follow_redirects=True)
            ct = t.headers.get("Content-Type", "")
            if t.status_code == 200 and ct.startswith("image/"):
                return t.content, ct
            return descargar_media(cfg, file_id)
        token = _access_token(cfg)
        r = httpx.get(f"https://www.googleapis.com/drive/v3/files/{file_id}", params={
            "fields": "thumbnailLink", "supportsAllDrives": "true"},
            headers={"Authorization": f"Bearer {token}"}, timeout=20)
        link = r.json().get("thumbnailLink") if r.status_code == 200 else None
        if not link:
            return descargar_media(cfg, file_id)
        base = link.split("=s")[0]
        t = httpx.get(f"{base}=s{size}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if t.status_code != 200:
            return descargar_media(cfg, file_id)
        return t.content, t.headers.get("Content-Type", "image/jpeg")
    except Exception:  # noqa: BLE001
        return None


def descargar(cfg: dict, file_id: str) -> Optional[bytes]:
    """Descarga el contenido de un fichero de Drive (alt=media). None si falla."""
    try:
        extra, headers = _read_auth(cfg)
        r = httpx.get(f"https://www.googleapis.com/drive/v3/files/{file_id}",
                      params={"alt": "media", "supportsAllDrives": "true", **extra},
                      headers=headers, timeout=60)
        return r.content if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def mover_fichero(cfg: dict, file_id: str, add_parent: str, remove_parent: str) -> bool:
    """Mueve un fichero entre carpetas (conserva id y webViewLink → no rompe enlaces guardados)."""
    try:
        token = _access_token(cfg)
        r = httpx.patch(f"https://www.googleapis.com/drive/v3/files/{file_id}", params={
            "addParents": add_parent, "removeParents": remove_parent,
            "supportsAllDrives": "true", "fields": "id"},
            headers={"Authorization": f"Bearer {token}"}, timeout=20)
        return r.status_code in (200, 201)
    except Exception:  # noqa: BLE001
        return False


def test(cfg: dict) -> dict:
    if not configurado(cfg):
        return {"ok": False, "error": "Faltan credenciales Drive"}
    try:
        _access_token(cfg)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
