"""Limpieza segura de disco (infraestructura) — reutilizada por la reparación reactiva
de Centinela (disco al 95%) y por el mantenimiento proactivo nocturno.

El ÚNICO repaso autónomo de Victor sobre el sistema de ficheros: borra SOLO caché/temporales
desechables y conocidos — nunca fotos de paciente, facturas, documentos ni backups (esos viven
en backend/media/, jamás tocados aquí). Antigüedad mínima 24h para no rozar nada en uso:
  - /tmp/makingsmiles_pdfs/  → PDFs de casos de ortodoncia, regenerables bajo demanda.
  - /tmp/media_whatsapp_fallback/ → adjuntos de WhatsApp cuando falla el disco normal.
  - /tmp/tmp*.pdf → facturas/justificantes renderizados vía NamedTemporaryFile(delete=False)
    y ya servidos en la respuesta; nadie vuelve a leerlos.
"""
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_CORTE_HORAS = 24


def limpiar_temporales_seguros() -> dict:
    corte = time.time() - _CORTE_HORAS * 3600
    liberado = 0
    borrados = 0
    for d in (Path("/tmp/makingsmiles_pdfs"), Path("/tmp/media_whatsapp_fallback")):
        if not d.is_dir():
            continue
        for f in d.iterdir():
            try:
                if f.is_file() and f.stat().st_mtime < corte:
                    liberado += f.stat().st_size
                    f.unlink()
                    borrados += 1
            except Exception:  # raiz: disco/permisos: el fallo no bloquea la operacion; se degrada
                logger.debug("disco: temporal bloqueado, se omite", exc_info=True)
                continue
    for f in Path("/tmp").glob("tmp*.pdf"):
        try:
            if f.is_file() and f.stat().st_mtime < corte:
                liberado += f.stat().st_size
                f.unlink()
                borrados += 1
        except Exception:  # raiz: disco/permisos: el fallo no bloquea la operacion; se degrada
            logger.debug("disco: tmp*.pdf bloqueado, se omite", exc_info=True)
            continue
    return {"archivos_borrados": borrados, "mb_liberados": round(liberado / 1e6, 1)}
