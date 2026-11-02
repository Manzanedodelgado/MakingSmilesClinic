"""Servido AUTENTICADO de ficheros de /media (cierra C8).

ANTES: `app.mount("/media", StaticFiles(...))` servía TODO backend/media SIN autenticación
(consentimientos con firma, radiografías, facturas fiscales, documentos, media de WhatsApp)
→ descargable por cualquiera con nombres semi-adivinables.

AHORA: /media solo se sirve a una sesión válida (get_current_user), con guard anti-traversal.
  · Los medios CLÍNICOS del paciente (media/pacientes/**) NO se sirven crudos por aquí: van
    por el proxy anti-IDOR de multimedia_service (/pacientes/{id}/multimedia/{fileId}), que
    verifica paciente∈centro. Aquí se rechazan (404) para no dejar una puerta cruda.
  · La firma PÚBLICA de consentimiento (sin login) tiene su propia ruta gateada por el
    `signing_code` en consentimientos_router (/consentimientos/firmar/{code}/pdf).
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from api.auth_deps import CurrentUser, get_current_user

router = APIRouter(tags=["media"])

_MEDIA = (Path(__file__).resolve().parent.parent / "media").resolve()
# Subcarpetas cuyos ficheros NO se sirven crudos (tienen su propio endpoint scopeado).
_SOLO_PROXY = {"pacientes"}


@router.get("/media/{ruta:path}")
def servir_media(ruta: str, _user: CurrentUser = Depends(get_current_user)) -> FileResponse:
    """Sirve un fichero de /media a un usuario autenticado. 404 si sale de /media o es de un
    área que solo se sirve por su proxy scopeado."""
    destino = (_MEDIA / ruta).resolve()
    # Anti-traversal: el fichero DEBE quedar dentro de /media.
    if destino != _MEDIA and _MEDIA not in destino.parents:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    try:
        rel = destino.relative_to(_MEDIA)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    # Medios clínicos del paciente: solo por el proxy anti-IDOR, nunca crudos.
    if rel.parts and rel.parts[0] in _SOLO_PROXY:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    if not destino.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    return FileResponse(destino, headers={"Cache-Control": "private, max-age=300"})
