"""Acceso al archivo de documentos en Google Drive.

Solo lectura y movimiento de ficheros: qué documentos hay, cómo se descarga uno y cómo se
traslada de carpeta. Nada de interpretar su contenido — de eso se ocupa la lectura fiscal.

Se apoya en `infrastructure.external_apis.drive_client`, que ya resuelve la autenticación
con la cuenta de servicio.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from infrastructure.external_apis import drive_client

logger = logging.getLogger(__name__)

_API = "https://www.googleapis.com/drive/v3/files"
_ESPERA = 60


def inventario(cfg: dict, carpeta_id: str) -> list[dict[str, Any]]:
    """Todos los documentos de una carpeta, recorriendo también sus subcarpetas.

    Se pide `supportsAllDrives`/`includeItemsFromAllDrives` porque el archivo vive en una
    unidad compartida: sin esos parámetros la API devuelve la carpeta vacía.

    El orden es alfabético por nombre. Los nombres empiezan por fecha
    (`2019-07-17_237_FNMT_RCM_...`), así que ordenar por nombre es ordenar por antigüedad,
    que es como se quiere revisar el archivo: de la más vieja a la más nueva.
    """
    try:
        token = drive_client._access_token(cfg)
    except Exception:                                   # raiz: sin token de Drive no hay archivo
        logger.warning("gestor-archivo: Drive sin token", exc_info=True)
        return []

    documentos: list[dict[str, Any]] = []
    pendientes = [carpeta_id]
    while pendientes:
        actual = pendientes.pop(0)
        pagina: Optional[str] = None
        while True:
            parametros = {
                "q": f"'{actual}' in parents and trashed=false",
                "fields": "files(id,name,mimeType,size),nextPageToken",
                "pageSize": "1000",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if pagina:
                parametros["pageToken"] = pagina
            try:
                datos = httpx.get(_API, params=parametros,
                                  headers={"Authorization": f"Bearer {token}"},
                                  timeout=_ESPERA).json()
            except Exception:  # raiz: listado de Drive falla a mitad → inventario parcial
                logger.warning("gestor-archivo: listado Drive parcial", exc_info=True)
                break
            for f in datos.get("files", []):
                if f.get("mimeType") == "application/vnd.google-apps.folder":
                    pendientes.append(f["id"])
                else:
                    f["_carpeta"] = actual
                    documentos.append(f)
            pagina = datos.get("nextPageToken")
            if not pagina:
                break

    return sorted(documentos, key=lambda f: str(f.get("name", "")))


def descargar(cfg: dict, file_id: str) -> Optional[bytes]:
    """El contenido binario de un documento."""
    return drive_client.descargar(cfg, file_id)


def mover(cfg: dict, file_id: str, destino: str, origen: str) -> bool:
    """Traslada un documento de una carpeta a otra."""
    return drive_client.mover_fichero(cfg, file_id, destino, origen)


def carpeta_del_anio(cfg: dict, raiz: str, anio: str) -> Optional[str]:
    """La subcarpeta del año dentro del archivo, creándola si no existe."""
    return drive_client.buscar_o_crear_carpeta(cfg, anio, raiz)


def renombrar(cfg: dict, file_id: str, nombre: str) -> bool:
    """Cambia el nombre de un documento en Drive."""
    try:
        token = drive_client._access_token(cfg)
    except Exception:  # raiz: sin token de Drive → no se puede renombrar
        logger.warning("gestor-archivo: renombrar sin token", exc_info=True)
        return False
    try:
        respuesta = httpx.patch(
            f"{_API}/{file_id}",
            params={"supportsAllDrives": "true", "fields": "id,name"},
            json={"name": nombre},
            headers={"Authorization": f"Bearer {token}"},
            timeout=_ESPERA)
        return respuesta.status_code == 200
    except Exception:  # raiz: fallo de red en el renombrado → sin renombrar
        logger.warning("gestor-archivo: patch de renombrado falló", exc_info=True)
        return False
