"""MULTIMEDIA — imágenes y radiografías del paciente desde varias fuentes:

  · LOCAL (filesystem): media/pacientes/«{num_historia} — APELLIDOS, Nombre»/{Imágenes,RX,…}
    (subcarpeta «RX»/«Radiografías»… → panorámicas; sueltos y el resto → fotos). La carpeta
    del paciente (con sus subcarpetas Imágenes/RX) se crea al abrir su ficha si no existe.
  · Google Drive (si la integración está activa): misma estructura en Drive.
  · Orthanc (PACS): instancias DICOM cuyo PatientID == num_historia → panorámicas.

Todas se sirven por PROXY autenticado: el frontend nunca ve la ruta/tokens y solo accede a
imágenes de SU paciente (guard anti-IDOR/traversal en cada fuente). El prefijo del id
(«local:» / «orthanc:» / —) distingue el origen en el endpoint de descarga.
"""
import base64
import datetime
import mimetypes
import re
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from domain.models.config import Integracion
from domain.models.core import Paciente
from infrastructure.external_apis import drive_client, orthanc_client

# Una subcarpeta es de radiografías si su nombre lo delata; el resto → fotos.
_RE_RX_DIR = re.compile(r"\brx\b|radiograf|ortopan|panor|cefal|cbct|periapical", re.I)
_ORTHANC = "orthanc:"
_LOCAL = "local:"

# Raíz local de medios de pacientes: backend/media/pacientes/
MEDIA_PAC = Path(__file__).resolve().parents[2] / "media" / "pacientes"
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic"}


def _mime(p: Path) -> str:
    return mimetypes.guess_type(p.name)[0] or "application/octet-stream"


def _enc(rel: str) -> str:   # ruta relativa → id sin barras (para que viaje en la URL)
    return base64.urlsafe_b64encode(rel.encode()).decode()


def _dec(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode()).decode()


def _safe(name: str) -> str:
    return (name or "").replace("/", "-").strip()


class MultimediaService:
    def __init__(self, session: Session):
        self.session = session

    # ── Config de fuentes externas (solo integraciones ACTIVAS) ──
    def _cfg(self, centro_id: int, tipo: str) -> Optional[dict]:
        ig = self.session.exec(select(Integracion).where(
            Integracion.centro_id == centro_id, Integracion.tipo == tipo,
            Integracion.activo == True)).first()  # noqa: E712
        return ig.config if ig else None

    def _drive_cfg(self, centro_id: int) -> Optional[dict]:
        # Solo LECTURA: basta una API key sobre la carpeta compartida por enlace
        # (el cliente OAuth quedó borrado por Google; ver integración id 9).
        cfg = self._cfg(centro_id, "google_drive")
        return cfg if drive_client.configurado_lectura(cfg) else None

    def _orthanc_cfg(self, centro_id: int) -> Optional[dict]:
        cfg = self._cfg(centro_id, "orthanc")
        return cfg if orthanc_client.configurado(cfg) else None

    # ── Fuente LOCAL (filesystem) ──
    def _nh_en_varios_centros(self, nh: str) -> bool:
        """True si el num_historia existe en más de un centro: el filesystem local agrupa
        carpetas por nh SIN centro y el nh se genera POR CENTRO, así que dos centros con el
        mismo nh compartirían carpeta → fuga cross-tenant. En ese caso la fuente local se
        desactiva para ese nh (fail-closed); Drive/Orthanc siguen aislados por credencial."""
        if not nh:
            return False
        centros = set(self.session.exec(
            select(Paciente.centro_id).where(
                Paciente.num_historia == nh, Paciente.centro_id.is_not(None))).all())
        return len(centros) > 1

    def _carpeta_local(self, paciente: Paciente, crear: bool = False) -> Optional[Path]:
        """Carpeta local del paciente (la busca por prefijo de num_historia; la crea si `crear`)."""
        nh = (paciente.num_historia or "").strip()
        if not nh or self._nh_en_varios_centros(nh):
            return None
        if MEDIA_PAC.exists():
            for d in MEDIA_PAC.iterdir():
                if d.is_dir() and (d.name.startswith(f"{nh} ") or d.name == nh):
                    return d
        if not crear:
            return None
        ape = (paciente.apellidos or "").strip()
        nom = (paciente.nombre or "").strip()
        etiqueta = f"{nh} — {ape}, {nom}".rstrip(" ,—").strip() if (ape or nom) else nh
        carpeta = MEDIA_PAC / _safe(etiqueta)
        # El backend corre como root; creamos abiertas (777) para que el equipo pueda dejar fotos.
        for d in (MEDIA_PAC, carpeta, carpeta / "Imágenes", carpeta / "RX"):
            d.mkdir(parents=True, exist_ok=True)
            try:
                d.chmod(0o777)
            except OSError:  # raiz: el permiso es cortesía; la carpeta vale sin él
                pass
        return carpeta

    def guardar_foto_paciente(self, centro_id: int, paciente: Paciente, contenido: bytes, nombre: str = None, subcarpeta: str = "Imágenes") -> Optional[Path]:
        """Guarda un medio en la carpeta del paciente (subcarpeta «Imágenes» = fotos, «RX» =
        radiografías) — la MISMA ubicación que lee la ficha de la web matriz. Así una foto o RX de
        la app/radiología aparece automáticamente en Multimedia. None si no hay num_historia."""
        # Defensa en profundidad: validar que el paciente pertenece al centro solicitante
        if paciente.centro_id != centro_id:
            return None
        carpeta = self._carpeta_local(paciente, crear=True)
        if not carpeta:
            return None
        destino = carpeta / _safe(subcarpeta) / _safe(nombre)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
        try:
            destino.chmod(0o666)
        except OSError:  # raiz: el permiso es cortesía; el fichero vale sin él
            pass
        return destino

    @staticmethod
    def _items_local(d: Path, base: Path) -> list[dict]:
        out: list[dict] = []
        if not d.is_dir():
            return out
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix.lower() in _IMG_EXT:
                rel = f.relative_to(base).as_posix()
                fecha = datetime.datetime.fromtimestamp(f.stat().st_mtime).date().isoformat()
                out.append({"id": f"{_LOCAL}{_enc(rel)}", "name": f.name, "fecha": fecha, "mime": _mime(f)})
        return out

    def _listar_local(self, carpeta: Path) -> tuple[list, list]:
        fotos = self._items_local(carpeta, carpeta)          # sueltos en la raíz → fotos
        rx: list[dict] = []
        for sub in sorted(p for p in carpeta.iterdir() if p.is_dir()):
            imgs = self._items_local(sub, carpeta)
            (rx if _RE_RX_DIR.search(sub.name) else fotos).extend(imgs)
        return fotos, rx

    @staticmethod
    def _item_drive(a: dict) -> dict:
        return {"id": a["id"], "name": a["name"], "fecha": a.get("createdTime"), "mime": a.get("mimeType")}

    @staticmethod
    def _item_orthanc(inst: dict) -> dict:
        t = inst.get("RequestedTags") or {}
        modality = t.get("Modality") or "RX"
        desc = t.get("StudyDescription") or t.get("SeriesDescription") or "Radiografía"
        sd = t.get("StudyDate") or ""
        fecha = f"{sd[0:4]}-{sd[4:6]}-{sd[6:8]}" if len(sd) == 8 else None
        return {"id": f"{_ORTHANC}{inst['ID']}", "name": f"{desc} · {modality}", "fecha": fecha, "mime": "image/jpeg"}

    def _carpeta_drive(self, cfg: dict, num_historia: str) -> Optional[str]:
        root = (cfg.get("carpetas") or {}).get("pacientes")
        if not root or not num_historia:
            return None
        return drive_client.buscar_subcarpeta_prefijo(cfg, root, f"{num_historia} ")

    def crear_carpeta_drive(self, centro_id: int, paciente: Paciente) -> Optional[str]:
        """Crea en Drive la carpeta del paciente «<num_historia> <apellidos> <nombre>» con sus
        subcarpetas «RX» e «Imágenes». Idempotente: si ya hay una carpeta que empiece por
        «<num_historia> » la reutiliza. Escribe con la service account (sin cuota propia, pero válida
        en carpetas de unidad compartida). Best-effort: None si no hay credencial/permiso; nunca lanza."""
        try:
            cfg = self._cfg(centro_id, "google_drive")
            nh = (paciente.num_historia or "").strip()
            root = ((cfg or {}).get("carpetas") or {}).get("pacientes")
            if not drive_client.configurado(cfg) or not nh or not root or paciente.centro_id != centro_id:
                return None
            folder = drive_client.buscar_subcarpeta_prefijo(cfg, root, f"{nh} ")
            if not folder:
                etiqueta = " ".join(f"{nh} {paciente.apellidos or ''} {paciente.nombre or ''}".split())
                folder = drive_client.buscar_o_crear_carpeta(cfg, _safe(etiqueta), root)
            if not folder:
                return None
            for sub in ("RX", "Imágenes"):
                drive_client.buscar_o_crear_carpeta(cfg, sub, folder)
            return folder
        except Exception:  # raiz: Drive no disponible -> sin carpeta; el fichero local sigue valido
            return None

    def subir_a_drive(self, centro_id: int, paciente: Paciente, contenido: bytes, nombre: str,
                      subcarpeta: str = "Imágenes", mime: str = "image/jpeg") -> Optional[str]:
        """Sube un medio a la carpeta del paciente en Drive, subcarpeta «Imágenes» (fotos) o «RX»
        (radiografías); crea la subcarpeta si no existe. Requiere credencial de ESCRITURA (OAuth/SA);
        con solo api_key (lectura) devuelve None. Devuelve el id del fichero o None."""
        cfg = self._drive_cfg(centro_id)
        nh = paciente.num_historia or ""
        # Defensa en profundidad: el paciente DEBE pertenecer al centro que aporta la
        # credencial (un llamante con IDs cruzados no sube a la carpeta de otro centro).
        if not cfg or not nh or paciente.centro_id != centro_id:
            return None
        folder = self._carpeta_drive(cfg, nh)   # búsqueda/lectura con la credencial que haya
        if not folder:
            return None
        # ESCRITURA: la service account no tiene cuota en «Mi unidad». La credencial que puede
        # escribir en la carpeta de PACIENTES es la OAuth de usuario (`oauth_borrado`). Se usa esa;
        # si no hay o falla la auth, no-op (None) — nunca rompe la subida original.
        cfg_w = dict(cfg)
        ob = cfg.get("oauth_borrado")
        if isinstance(ob, dict) and ob.get("refresh_token"):
            cfg_w = {k: v for k, v in cfg.items() if k != "sa_b64"}
            cfg_w.update(ob)
        destino = drive_client.buscar_o_crear_carpeta(cfg_w, _safe(subcarpeta), folder) or folder
        try:
            return drive_client.subir(cfg_w, filename=nombre, content=contenido, mime=mime, folder_id=destino).get("id")
        except Exception:  # raiz: Drive caido -> sin id remoto; no rompe la subida local
            return None

    # ── Foto de perfil desde Drive ──
    _RE_CARA = re.compile(r"^cara\.(jpe?g|png|webp)$", re.I)

    def buscar_foto_cara(self, centro_id: int, paciente: Paciente) -> Optional[tuple[bytes, str]]:
        """Busca «cara.jpeg» (o .jpg/.png/.webp, cualquier mayúscula) en la carpeta RAÍZ de
        Drive del paciente (no en Imágenes/RX) y devuelve (bytes, content-type). None si no hay
        integración Drive activa, no se encuentra la carpeta o el fichero."""
        # Defense in depth: never search a Drive account using a patient from another center.
        if paciente.centro_id != centro_id:
            return None
        cfg = self._drive_cfg(centro_id)
        nh = paciente.num_historia or ""
        if not cfg or not nh:
            return None
        folder = self._carpeta_drive(cfg, nh)
        if not folder:
            return None
        archivo = next((a for a in drive_client.listar_imagenes(cfg, folder)
                        if self._RE_CARA.match((a.get("name") or "").strip())), None)
        if not archivo:
            return None
        return drive_client.descargar_media(cfg, archivo["id"])

    # ── Listado ──
    def listar(self, centro_id: int, paciente: Paciente) -> dict:
        nh = paciente.num_historia or ""
        fotos: list[dict] = []
        rx: list[dict] = []
        fuentes: list[str] = []

        # LOCAL (fuente principal) — crea la carpeta del paciente si no existe.
        fuentes.append("local")
        carpeta = self._carpeta_local(paciente, crear=True)
        if carpeta:
            f2, r2 = self._listar_local(carpeta)
            fotos += f2
            rx += r2

        # Orthanc (PACS) — se calcula antes para no duplicar sus RX con la copia-archivo de Drive.
        ocfg = self._orthanc_cfg(centro_id)

        # Google Drive (solo si la integración está activa)
        dcfg = self._drive_cfg(centro_id)
        if dcfg:
            fuentes.append("drive")
            folder = self._carpeta_drive(dcfg, nh)
            if folder:
                fotos += [self._item_drive(a) for a in drive_client.listar_imagenes(dcfg, folder)]
                for sub in drive_client.listar_subcarpetas(dcfg, folder):
                    imgs = [self._item_drive(a) for a in drive_client.listar_imagenes(dcfg, sub["id"])]
                    es_rx = bool(_RE_RX_DIR.search(sub.get("name") or ""))
                    # Con Orthanc activo, las copias-archivo «orthanc_…» ya se ven vía PACS: no duplicar.
                    if es_rx and ocfg:
                        imgs = [a for a in imgs if not (a.get("name") or "").startswith("orthanc_")]
                    (rx if es_rx else fotos).extend(imgs)

        # Orthanc (PACS): instancias en vivo por PatientID.
        if ocfg and nh:
            fuentes.append("orthanc")
            rx += [self._item_orthanc(i) for i in orthanc_client.buscar_instancias(ocfg, nh)]

        return {"disponible": True, "fuentes": fuentes, "fotos": fotos, "radiografias": rx}

    # ── Series DICOM (visor de cortes) ──
    def series_dicom(self, centro_id: int, paciente: Paciente) -> list[dict]:
        """Series DICOM del paciente en Orthanc (cortes ordenados). Vacío si no hay PACS/num_historia."""
        cfg = self._orthanc_cfg(centro_id)
        nh = paciente.num_historia or ""
        if not cfg or not nh:
            return []
        return orthanc_client.series_de_paciente(cfg, nh)

    # ── Descarga (proxy) ──
    def media(self, centro_id: int, paciente: Paciente, file_id: str, thumb: bool = False) -> Optional[tuple[bytes, str]]:
        nh = paciente.num_historia or ""
        if file_id.startswith(_LOCAL):
            return self._media_local(paciente, file_id[len(_LOCAL):])
        if file_id.startswith(_ORTHANC):
            return self._media_orthanc(centro_id, nh, file_id[len(_ORTHANC):], thumb)
        return self._media_drive(centro_id, nh, file_id, thumb)

    def _media_local(self, paciente: Paciente, enc_rel: str) -> Optional[tuple[bytes, str]]:
        carpeta = self._carpeta_local(paciente)
        if not carpeta:
            return None
        try:
            rel = _dec(enc_rel)
        except Exception:  # raiz: ruta codificada corrupta -> None; nunca se sirve fuera de la carpeta
            return None
        base = carpeta.resolve()
        target = (carpeta / rel).resolve()
        # anti-traversal: el fichero DEBE estar dentro de la carpeta del paciente.
        if base != target and base not in target.parents:
            return None
        if not target.is_file() or target.suffix.lower() not in _IMG_EXT:
            return None
        return target.read_bytes(), _mime(target)

    def _media_orthanc(self, centro_id: int, num_historia: str, instance_id: str, thumb: bool) -> Optional[tuple[bytes, str]]:
        cfg = self._orthanc_cfg(centro_id)
        if not cfg or not num_historia:
            return None
        # Guard anti-IDOR: la instancia DEBE pertenecer a este paciente (PatientID == num_historia).
        if orthanc_client.patient_id_de_instancia(cfg, instance_id) != num_historia:
            return None
        return orthanc_client.rendered(cfg, instance_id, 480 if thumb else None)

    def _media_drive(self, centro_id: int, num_historia: str, file_id: str, thumb: bool) -> Optional[tuple[bytes, str]]:
        cfg = self._drive_cfg(centro_id)
        if not cfg:
            return None
        folder = self._carpeta_drive(cfg, num_historia)
        if not folder:
            return None
        # Guard anti-IDOR: el fichero DEBE estar entre los medios enumerados de ESTE paciente
        # (carpeta + subcarpetas). Comprobamos pertenencia por id en vez del campo `parents`,
        # porque con API key (carpeta compartida) Drive omite `parents`.
        permitidos = {a["id"] for a in drive_client.listar_imagenes(cfg, folder)}
        for sub in drive_client.listar_subcarpetas(cfg, folder):
            permitidos |= {a["id"] for a in drive_client.listar_imagenes(cfg, sub["id"])}
        if file_id not in permitidos:
            return None
        return drive_client.thumbnail(cfg, file_id, 480) if thumb else drive_client.descargar_media(cfg, file_id)
