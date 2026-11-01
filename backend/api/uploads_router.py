"""Subida de imágenes (logo/icono/sello). Guarda fichero y devuelve URL (nunca base64)."""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from api.auth_deps import CurrentUser, require_permission

router = APIRouter(prefix="/uploads", tags=["uploads"])
MEDIA = Path(__file__).resolve().parent.parent / "media"
EXT_OK = {"png", "jpg", "jpeg", "webp"}
MAX_BYTES = 10 * 1024 * 1024


def _mime_valido(ext: str, contenido: bytes) -> bool:
    """Comprueba la firma del formato; no confía en nombre ni Content-Type del cliente."""
    if ext in {"jpg", "jpeg"}:
        return contenido.startswith(b"\xff\xd8\xff")
    if ext == "png":
        return contenido.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == "webp":
        return len(contenido) >= 12 and contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP"
    return False


@router.post("", status_code=201)
async def subir(file: UploadFile = File(...), _user: CurrentUser = Depends(require_permission("config.editar"))) -> dict:
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in EXT_OK:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Formato no admitido ({', '.join(sorted(EXT_OK))})")
    contenido = await file.read(MAX_BYTES + 1)
    if not contenido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Archivo vacío")
    if len(contenido) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "La imagen supera el máximo (10 MB)")
    if not _mime_valido(ext, contenido):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El contenido no coincide con el formato indicado")
    MEDIA.mkdir(parents=True, exist_ok=True)
    nombre = f"{uuid.uuid4().hex}.{ext}"
    (MEDIA / nombre).write_bytes(contenido)
    return {"url": f"/media/{nombre}"}
