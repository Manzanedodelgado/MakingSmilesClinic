"""🛡️ CENTINELA — copias de seguridad programadas.

Qué se copia y por qué:
  · `makingsmiles`           → los datos de la clínica (pacientes, citas, económico).
  · `makingsmiles_platform`  → el registro de centros del SuperUser: vive en una BBDD
                               FÍSICAMENTE SEPARADA, así que copiar solo la operativa
                               dejaría fuera a qué centros existen y con qué plan.
  · `evolution`              → historial de WhatsApp (conversaciones con pacientes) y la
                               sesión de la instancia; sin esto habría que reemparejar.
  · `media/`                 → fotos, radiografías subidas, documentos y consentimientos
                               FIRMADOS. No están en la BBDD: si se pierden, no se
                               regeneran.

Cómo:
  · `pg_dump -Fc` (formato propio, comprimido) hablando con Postgres por la red interna
    de Docker. No se usa `docker exec` contra el contenedor de Postgres: está bloqueado a
    propósito en el proxy de Docker (ver infrastructure/docker_client.py).
  · Cada volcado se VERIFICA con `pg_restore --list` antes de darlo por bueno. Un fichero
    truncado o corrupto pesa y parece una copia, pero no restaura: sin esta comprobación
    el fallo se descubre el día que hace falta, que es el peor día posible.
  · El envío fuera del servidor va por `rsync` sobre SSH. `rsync` es incremental, así que
    los 266 MB de `media/` solo viajan la primera vez; después solo lo que cambió.
  · NUNCA se usa `--delete`: una copia de seguridad no debe propagar borrados. Si alguien
    borra una foto aquí, la copia de allí se queda.

Todo queda en `auditoria` (`centinela.backup.*`) y, si falla, Centinela avisa por sus
canales configurados igual que con cualquier otra incidencia.
"""
import os
import shutil
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from sqlmodel import Session

from application.services.auth_service import AuthService
from domain.config.settings import settings

# Bases de datos a copiar. `evolution` puede no existir en una instalación sin WhatsApp:
# su ausencia NO se considera fallo (se registra como omitida).
BASES = ("makingsmiles", "makingsmiles_platform", "evolution")

ACCION_OK = "centinela.backup.ok"
ACCION_FALLO = "centinela.backup.fallo"


def _conexion() -> dict:
    """Datos de conexión sacados de DATABASE_URL (no se duplican en otro sitio)."""
    u = urlparse(settings.database_url.replace("postgresql+psycopg://", "postgresql://"))
    return {"host": u.hostname or "postgres", "port": str(u.port or 5432),
            "user": u.username or "makingsmiles", "password": u.password or ""}


def _ejecutar(cmd: list[str], *, env: Optional[dict] = None, timeout: int = 1800) -> tuple[bool, str]:
    entorno = {**os.environ, **(env or {})}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=entorno)
    except subprocess.TimeoutExpired:
        return False, f"tiempo agotado ({timeout}s)"
    except FileNotFoundError as e:
        return False, f"falta la herramienta: {e}"
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "").strip()[:400]
    return True, (r.stdout or "").strip()


class BackupService:
    def __init__(self, session: Session):
        self.session = session

    # ─────────────────────────── copia completa ───────────────────────────
    def ejecutar(self, *, centro_id: Optional[int] = None) -> dict:
        inicio = datetime.now()
        sello = inicio.strftime("%Y%m%d-%H%M")
        destino_local = Path(settings.backup_dir) / sello
        destino_local.mkdir(parents=True, exist_ok=True)

        conn = _conexion()
        resultado: dict = {"sello": sello, "bases": {}, "media": None, "servidor": None,
                           "remoto": None, "errores": []}

        # 1) Volcado + verificación de cada base
        for base in BASES:
            fichero = destino_local / f"{base}.dump"
            ok, err = _ejecutar([
                "pg_dump", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"],
                "-d", base, "-Fc", "-f", str(fichero),
            ], env={"PGPASSWORD": conn["password"]})
            if not ok:
                # Una base inexistente no es un fallo de la copia (instalación sin WhatsApp).
                if "does not exist" in err or "no existe" in err:
                    resultado["bases"][base] = "omitida (no existe)"
                    fichero.unlink(missing_ok=True)
                    continue
                resultado["bases"][base] = f"ERROR: {err[:200]}"
                resultado["errores"].append(f"{base}: {err[:200]}")
                continue

            # Verificación real: si pg_restore no puede listar el contenido, el fichero
            # no sirve para restaurar por mucho que ocupe.
            ok_v, err_v = _ejecutar(["pg_restore", "--list", str(fichero)], timeout=300)
            if not ok_v:
                resultado["bases"][base] = f"CORRUPTA: {err_v[:200]}"
                resultado["errores"].append(f"{base}: volcado ilegible ({err_v[:120]})")
                continue
            resultado["bases"][base] = f"{fichero.stat().st_size / 1e6:.1f} MB · verificada"

        # 2) Media (fotos, documentos, consentimientos firmados)
        media = Path(settings.backup_media_dir)
        if media.is_dir():
            try:
                tar_path = destino_local / "media.tar.gz"
                with tarfile.open(tar_path, "w:gz") as tar:
                    tar.add(media, arcname="media")
                resultado["media"] = f"{tar_path.stat().st_size / 1e6:.1f} MB"
            except Exception as e:  # raiz: copia de seguridad: un fallo de un paso no tumba el resto; se registra
                resultado["media"] = f"ERROR: {e}"
                resultado["errores"].append(f"media: {e}")
        else:
            resultado["media"] = "sin carpeta media"

        # 3) Configuración del SERVIDOR. Sin esto la copia deja una BBDD llena y nada que
        #    la sirva: los secretos (.env) sin los que el stack no arranca, el Caddyfile con
        #    la página de respaldo, las unidades de systemd que levantan la web y el índice
        #    de Orthanc. Ocupa unos cientos de KB y es la diferencia entre "tengo los datos"
        #    y "puedo volver a levantar esto".
        srv = Path(settings.backup_servidor_dir)
        if srv.is_dir():
            try:
                tar_srv = destino_local / "servidor.tar.gz"
                with tarfile.open(tar_srv, "w:gz") as tar:
                    tar.add(srv, arcname="servidor")
                resultado["servidor"] = f"{tar_srv.stat().st_size / 1024:.0f} KB"
            except Exception as e:  # raiz: copia de seguridad: un fallo de un paso no tumba el resto; se registra
                resultado["servidor"] = f"ERROR: {e}"
                resultado["errores"].append(f"servidor: {e}")
        else:
            resultado["servidor"] = "sin carpeta de configuración montada"

        # 4) Fuera del servidor. Una copia que vive en la misma máquina que los datos no
        #    protege del fallo que más importa (disco, borrado, cifrado por ransomware).
        resultado["remoto"] = self._enviar_fuera(destino_local)
        if resultado["remoto"].startswith("ERROR") or resultado["remoto"].startswith("SIN DESTINO"):
            resultado["errores"].append(f"envío remoto: {resultado['remoto'][:200]}")

        # 5) Retención local
        resultado["purgadas"] = self._purgar_locales()

        resultado["duracion_seg"] = round((datetime.now() - inicio).total_seconds(), 1)
        exito = not resultado["errores"]
        self._auditar(exito, resultado, centro_id)
        return {**resultado, "exito": exito}

    # ─────────────────────────── envío fuera del servidor ───────────────────────────
    def _enviar_fuera(self, carpeta: Path) -> str:
        destino = (settings.backup_destino or "").strip()
        if not destino:
            return ("SIN DESTINO configurado (BACKUP_DESTINO). La copia existe solo en este "
                    "servidor, que es justo lo que no protege de un fallo de disco.")
        opciones = ["-az", "--partial", "--timeout=600"]
        if settings.backup_ssh_key:
            opciones += ["-e", f"ssh -i {settings.backup_ssh_key} -o StrictHostKeyChecking=accept-new "
                               f"-o ConnectTimeout=15"]
        else:
            opciones += ["-e", "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"]
        # Sin --delete: la copia no propaga borrados (ver cabecera del módulo).
        ok, err = _ejecutar(["rsync", *opciones, str(carpeta), destino.rstrip("/") + "/"], timeout=3600)
        if not ok:
            return f"ERROR: {err[:300]}"
        return f"enviado a {destino}"

    # ─────────────────────────── retención ───────────────────────────
    def _purgar_locales(self) -> int:
        raiz = Path(settings.backup_dir)
        if not raiz.is_dir():
            return 0
        copias = sorted([d for d in raiz.iterdir() if d.is_dir()], key=lambda d: d.name)
        sobran = len(copias) - int(settings.backup_retencion_copias or 14)
        borradas = 0
        for d in copias[:max(0, sobran)]:
            try:
                shutil.rmtree(d)
                borradas += 1
            except Exception:  # raiz: copia de seguridad: un fallo de un paso no tumba el resto; se registra
                continue
        return borradas

    # ─────────────────────────── bitácora ───────────────────────────
    def _auditar(self, exito: bool, detalle: dict, centro_id: Optional[int]) -> None:
        try:
            AuthService(self.session).audit(
                ACCION_OK if exito else ACCION_FALLO, centro_id=centro_id,
                recurso=detalle.get("sello"), detalle=detalle, exito=exito)
        except Exception:  # raiz: copia de seguridad: un fallo de un paso no tumba el resto; se registra
            self.session.rollback()
