"""Cliente REST de Orthanc (servidor DICOM/PACS) — infraestructura.

Config en `integraciones` (tipo='orthanc'): {url, username, password, patient_id_field}.
Se consulta por PatientID (= num_historia del paciente, según la convención del centro) y
las imágenes se renderizan a JPEG por el endpoint /rendered (proxy desde el backend; el
frontend nunca habla con Orthanc ni ve credenciales).
"""
import base64
from typing import Optional

import httpx


def configurado(cfg: Optional[dict]) -> bool:
    return bool(cfg and cfg.get("url"))


def ping(cfg: dict) -> dict:
    """Comprobación barata de salud (para Centinela): GET /system, sin tocar datos DICOM."""
    try:
        r = httpx.get(f"{cfg['url']}/system", headers=_headers(cfg), timeout=10)
        if r.status_code == 200:
            return {"ok": True}
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:  # raiz: cliente externo: fallo de red/HTTP degrada a {ok:False}; nunca rompe al llamador
        return {"ok": False, "error": str(e)}


def _headers(cfg: dict) -> dict:
    u, p = cfg.get("username", ""), cfg.get("password", "")
    if not u:
        return {}
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def buscar_instancias(cfg: dict, patient_id: str) -> list[dict]:
    """Instancias DICOM cuyo PatientID == `patient_id`, con sus tags principales.
    Lista vacía si falla o no hay coincidencias."""
    if not patient_id:
        return []
    body = {
        "Level": "Instance",
        "Query": {"PatientID": patient_id},
        "Expand": True,
        "RequestedTags": ["StudyDate", "Modality", "StudyDescription", "SeriesDescription", "PatientID"],
    }
    try:
        r = httpx.post(f"{cfg['url']}/tools/find", json=body, headers=_headers(cfg), timeout=15)
        return r.json() if r.status_code == 200 else []
    except Exception:  # raiz: cliente externo: fallo de red/HTTP/parseo degrada (None/False); nunca rompe al llamador
        return []


def series_de_paciente(cfg: dict, patient_id: str) -> list[dict]:
    """Series DICOM del paciente (PatientID) con sus instancias ORDENADAS por InstanceNumber.
    Cada serie: {series_id, modalidad, descripcion, fecha, instancias:[instance_id...]}."""
    insts = buscar_instancias(cfg, patient_id)
    grupos: dict[str, list[dict]] = {}
    for it in insts:
        ps = it.get("ParentSeries")
        if ps:
            grupos.setdefault(ps, []).append(it)

    def _num(it: dict) -> int:
        try:
            return int(it.get("MainDicomTags", {}).get("InstanceNumber") or it.get("IndexInSeries") or 0)
        except (TypeError, ValueError):
            return it.get("IndexInSeries") or 0

    series = []
    for sid, items in grupos.items():
        items.sort(key=_num)
        t = items[0].get("RequestedTags") or {}
        sd = t.get("StudyDate") or ""
        fecha = f"{sd[0:4]}-{sd[4:6]}-{sd[6:8]}" if len(sd) == 8 else None
        series.append({
            "series_id": sid,
            "modalidad": t.get("Modality") or "",
            "descripcion": t.get("SeriesDescription") or t.get("StudyDescription") or "Serie DICOM",
            "fecha": fecha,
            "instancias": [it["ID"] for it in items],
        })
    series.sort(key=lambda s: s.get("fecha") or "", reverse=True)
    return series


def patient_id_de_instancia(cfg: dict, instance_id: str) -> Optional[str]:
    """PatientID (tag DICOM) de una instancia — para el guard anti-IDOR. None si falla."""
    try:
        r = httpx.get(f"{cfg['url']}/instances/{instance_id}/tags", params={"simplify": ""},
                      headers=_headers(cfg), timeout=10)
        return r.json().get("PatientID") if r.status_code == 200 else None
    except Exception:  # raiz: cliente externo: fallo de red/HTTP/parseo degrada (None/False); nunca rompe al llamador
        return None


def get_changes(cfg: dict, since: int = 0, limit: int = 100) -> Optional[dict]:
    """Feed de cambios de Orthanc desde `since`: {Changes:[{ChangeType,ResourceType,ID,Seq,Date}],
    Done:bool, Last:int}. Es como el detector sabe qué instancias son NUEVAS. None si falla."""
    try:
        r = httpx.get(f"{cfg['url']}/changes", params={"since": since, "limit": limit},
                      headers=_headers(cfg), timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception:  # raiz: cliente externo: fallo de red/HTTP/parseo degrada (None/False); nunca rompe al llamador
        return None


def tags_de_instancia(cfg: dict, instance_id: str) -> dict:
    """Tags DICOM simplificados de una instancia (PatientID, StudyDate, Modality, SOPInstanceUID…).
    Dict vacío si falla."""
    try:
        r = httpx.get(f"{cfg['url']}/instances/{instance_id}/tags", params={"simplify": ""},
                      headers=_headers(cfg), timeout=10)
        return r.json() if r.status_code == 200 else {}
    except Exception:  # raiz: cliente externo: fallo de red/HTTP/parseo degrada (None/False); nunca rompe al llamador
        return {}


def rendered(cfg: dict, instance_id: str, width: Optional[int] = None) -> Optional[tuple[bytes, str]]:
    """(bytes, mime) de la instancia renderizada a imagen (con ventana DICOM aplicada).
    `width` reduce el tamaño (miniatura). None si falla."""
    try:
        params = {"width": width} if width else {}
        r = httpx.get(f"{cfg['url']}/instances/{instance_id}/rendered", params=params,
                      headers=_headers(cfg), timeout=30)
        if r.status_code != 200:
            return None
        return r.content, r.headers.get("Content-Type", "image/jpeg")
    except Exception:  # raiz: cliente externo: fallo de red/HTTP/parseo degrada (None/False); nunca rompe al llamador
        return None
