"""Archivado del fichero de extracto bancario TAL CUAL se subió.

La app extrae los apuntes del extracto (PDF/XLSX/CSV) y hasta ahora descartaba el fichero.
Aquí se guarda el ORIGINAL, byte a byte, como soporte documental: la asesoría necesita
poder descargar exactamente lo que entregó el banco, no una reconstrucción.

Se guarda en `/media/extractos` (servido por `media_router` SOLO autenticado, nunca como
estático público — misma regla que el resto de medios con datos sensibles).
"""
import hashlib
import re
import uuid
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from domain.models.gestoria import ExtractoSubido

MEDIA_EXTRACTOS = Path(__file__).resolve().parents[2] / "media" / "extractos"

# Extensiones que el importador sabe leer; cualquier otra se guarda sin extensión conocida.
_EXT_OK = {".pdf", ".xlsx", ".xlsm", ".xls", ".csv", ".txt", ".tsv"}

_MIME = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".tsv": "text/tab-separated-values",
}


def _ext_de(nombre: str) -> str:
    ext = Path((nombre or "").lower()).suffix
    return ext if ext in _EXT_OK else ""


def _nombre_seguro(nombre: str) -> str:
    """Nombre legible para la descarga (el del disco es un uuid, no adivinable)."""
    limpio = re.sub(r"[^a-zA-Z0-9._ -]+", "_", (nombre or "")).strip(" _")
    return limpio[:200] or "extracto"


def archivar_extracto(session: Session, centro_id: int, contenido: bytes, *,
                      nombre_original: str, usuario_id: Optional[int] = None,
                      importados: int = 0, omitidos: int = 0) -> ExtractoSubido:
    """Guarda el fichero en disco y registra la subida. Devuelve el registro creado.

    El nombre en disco es un uuid (no adivinable): aunque `/media` exige autenticación,
    no se exponen nombres de fichero que revelen información. El nombre real que ve el
    usuario al descargar se guarda en `nombre_original`.
    """
    MEDIA_EXTRACTOS.mkdir(parents=True, exist_ok=True)
    ext = _ext_de(nombre_original)
    nombre_disco = f"{uuid.uuid4().hex}{ext}"
    (MEDIA_EXTRACTOS / nombre_disco).write_bytes(contenido)

    reg = ExtractoSubido(
        centro_id=centro_id,
        nombre_original=_nombre_seguro(nombre_original),
        archivo_url=f"/media/extractos/{nombre_disco}",
        mime=_MIME.get(ext),
        tamano_bytes=len(contenido),
        hash_sha256=hashlib.sha256(contenido).hexdigest(),
        subido_por=usuario_id,
        apuntes_importados=importados,
        apuntes_omitidos=omitidos,
    )
    session.add(reg)
    session.commit()
    session.refresh(reg)
    return reg
