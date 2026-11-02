"""Detector de RX nuevas → exportación a Drive (archivo del paciente).

El PACS (Orthanc) es el punto de detección: cuando una RX nueva entra en Orthanc (la sube el
feeder desde Romexis por REST, sin necesidad de licencia DICOM), su feed `/changes` la delata.
Este servicio, corrido periódicamente por el scheduler:

  1. Lee el feed de cambios de Orthanc desde el último `Seq` procesado (guardado en CONFIG).
  2. Por cada instancia NUEVA no vista aún (dedup en `rx_exportada`):
       · casa el paciente por PatientID == num_historia (convención del centro),
       · renderiza la RX a JPEG,
       · la sube a Drive → carpeta del paciente → subcarpeta «RX» (archivo, como las fotos).
  3. Registra el resultado (exportada / sin_paciente / error) para no reprocesarla.

La ficha ya muestra las RX de Orthanc en vivo; la copia en Drive es el ARCHIVO (offsite). Por eso
las copias se nombran «orthanc_…» y la ficha las omite del listado de Drive cuando Orthanc está
activo (evita duplicados). Best-effort: nada aquí puede tumbar el scheduler.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session, select

from application.services.config_service import ConfigService
from application.services.multimedia_service import MultimediaService
from domain.models.clinico import RxExportada
from domain.models.config import Integracion
from domain.models.core import Paciente
from infrastructure.external_apis import orthanc_client

log = logging.getLogger("radiologia.export")

_CLAVE_SEQ = "rx_export.orthanc_last_seq"
_SISTEMA = "radiologia"
# Prefijo de las copias que crea el detector en Drive → la ficha las omite si Orthanc está activo.
NOMBRE_PREFIJO = "orthanc_"


def _centros_con_orthanc(session: Session) -> list[int]:
    filas = session.exec(select(Integracion).where(
        Integracion.tipo == "orthanc", Integracion.activo == True)).all()  # noqa: E712
    return [ig.centro_id for ig in filas if ig.centro_id and orthanc_client.configurado(ig.config)]


def detectar_y_exportar(session: Session, centro_id: Optional[int] = None) -> dict:
    """Procesa las RX nuevas de Orthanc y las exporta a Drive. Devuelve un resumen."""
    centros = [centro_id] if centro_id else _centros_con_orthanc(session)
    total = {"centros": 0, "procesadas": 0, "exportadas": 0, "sin_paciente": 0, "errores": 0}
    for cid in centros:
        total["centros"] += 1
        try:
            _procesar_centro(session, cid, total)
        except Exception as e:  # raiz: detector de un centro falla, best-effort
            log.warning("detector RX: centro %s falló: %s", cid, e)
    return total


def _procesar_centro(session: Session, cid: int, total: dict) -> None:
    mm = MultimediaService(session)
    ocfg = mm._orthanc_cfg(cid)
    if not ocfg:
        return
    cfg_svc = ConfigService(session)
    last = int(cfg_svc.resolve(_CLAVE_SEQ, centro_id=cid, sistema=_SISTEMA, default=0) or 0)
    nuevo_last = last
    # Recorre el feed en páginas hasta agotarlo (Done).
    for _ in range(1000):   # tope defensivo: nunca bucle infinito
        data = orthanc_client.get_changes(ocfg, since=nuevo_last, limit=100)
        if not data:
            break
        cambios = data.get("Changes", [])
        for ch in cambios:
            seq = int(ch.get("Seq") or nuevo_last)
            if ch.get("ChangeType") == "NewInstance" and ch.get("ResourceType") == "Instance":
                _procesar_instancia(session, cid, ocfg, mm, ch.get("ID"), total)
            nuevo_last = max(nuevo_last, seq)
        if data.get("Done") or not cambios:
            break
    if nuevo_last != last:
        cfg_svc.set(_CLAVE_SEQ, nuevo_last, centro_id=cid, sistema=_SISTEMA)


def _procesar_instancia(session: Session, cid: int, ocfg: dict, mm: MultimediaService,
                        instance_id: Optional[str], total: dict) -> None:
    if not instance_id:
        return
    # DEDUP: ¿ya procesada?
    if session.exec(select(RxExportada).where(
            RxExportada.centro_id == cid, RxExportada.instance_id == instance_id)).first():
        return
    total["procesadas"] += 1
    tags = orthanc_client.tags_de_instancia(ocfg, instance_id)
    pid = (tags.get("PatientID") or "").strip() or None
    reg = RxExportada(centro_id=cid, instance_id=instance_id, sop_uid=tags.get("SOPInstanceUID"),
                      patient_id_dicom=pid, modalidad=tags.get("Modality"))

    pac = None
    if pid:
        pac = session.exec(select(Paciente).where(
            Paciente.centro_id == cid, Paciente.num_historia == str(pid))).first()
    if not pac:
        reg.estado = "sin_paciente"
        reg.detalle = f"PatientID '{pid}' sin ficha en el centro"
        total["sin_paciente"] += 1
        session.add(reg); session.commit()
        log.info("RX %s sin paciente (PatientID=%s)", instance_id, pid)
        return

    reg.paciente_id = pac.id
    reg.num_historia = pac.num_historia
    render = orthanc_client.rendered(ocfg, instance_id)
    if not render:
        reg.estado = "error"; reg.detalle = "No se pudo renderizar la instancia"
        total["errores"] += 1
        session.add(reg); session.commit()
        return
    contenido, mime = render
    ext = "jpg" if ("jpeg" in mime or "jpg" in mime) else ("png" if "png" in mime else "jpg")
    nombre = f"{NOMBRE_PREFIJO}{instance_id[:12]}.{ext}"
    try:
        drive_id = mm.subir_a_drive(cid, pac, contenido, nombre, subcarpeta="RX", mime=mime)
    except Exception as e:  # raiz: fallo subiendo a Drive, best-effort
        reg.estado = "error"; reg.detalle = f"Fallo subiendo a Drive: {e}"[:400]
        total["errores"] += 1
        session.add(reg); session.commit()
        log.warning("RX %s: fallo Drive: %s", instance_id, e)
        return
    reg.drive_file_id = drive_id
    reg.estado = "exportada"
    reg.detalle = None if drive_id else "Subida a Drive no disponible (sin credencial de escritura)"
    total["exportadas"] += 1
    session.add(reg); session.commit()
    log.info("RX %s exportada a Drive (paciente %s, drive_id=%s)", instance_id, pac.num_historia, drive_id)
