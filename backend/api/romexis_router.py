"""PUENTE DE PACIENTES web → Romexis (PMBridge).

Al crear un paciente en la web se encola aquí; un agente en el PC de Romexis consulta la cola,
mira Romexis por ID y actúa (crear / abrir / conflicto). Lógica de decisión:
  · no existe en Romexis                         → agente crea (DxStart)      → estado `creado`
  · existe con MISMO id + nombre + apellidos      → agente abre (DxStart)      → estado `abierto`
  · existe con MISMO id pero DISTINTO nombre       → estado `conflicto_id`; la web pregunta si
    modificar en Romexis. SÍ → `modificar` (agente lo cambia) → `resuelto`; NO → `nuevo_circuito`
    (ese id pudo asignarse a otro paciente por error → revisión manual).

Auth: endpoints del AGENTE por `X-Internal-Key`; endpoints de la WEB por sesión de centro.
"""
from __future__ import annotations
import hmac

from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.paciente_helper import _get_paciente
from domain.config.settings import settings
from domain.models.clinico import RomexisSync
from domain.models.core import Paciente
from infrastructure.config.db import engine, get_session

router = APIRouter(tags=["romexis · puente"])

_ESTADOS_AGENTE = {"pendiente", "modificar"}   # lo que el agente debe ejecutar


def _internal_auth(x_internal_key: Optional[str] = Header(default=None)) -> None:
    if not x_internal_key or not hmac.compare_digest(x_internal_key, settings.internal_api_key or ""):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clave interna inválida")


def _fecha_iso(f: Optional[date]) -> Optional[str]:
    """ISO (YYYY-MM-DD), sin asumir formato. El AGENTE la reformatea al formato regional que
    espera DxStart en el PC de Romexis (p. ej. DD/MM/YYYY en España)."""
    return f.isoformat() if f else None


def _encolar(session: Session, pac: Paciente) -> RomexisSync:
    """Encola (o reencola) la sincronización de un paciente hacia Romexis."""
    s = RomexisSync(centro_id=pac.centro_id, paciente_id=pac.id,
                    num_historia=pac.num_historia or "", apellidos=pac.apellidos or "",
                    nombre=pac.nombre or "", fecha_nacimiento=pac.fecha_nacimiento, estado="pendiente")
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


# ───────────────────────── ALTA de paciente en la web (dispara el puente) ─────────────────────────
class PacienteNuevoIn(BaseModel):
    """Alta con los campos de FILIACIÓN de columna directa del paciente. Los bloques
    relacionales (tarifas, seguro, facturación, anamnesis) se completan luego en la ficha."""
    nombre: str
    apellidos: str
    fecha_nacimiento: Optional[date] = None
    num_historia: Optional[str] = None   # NO editable: si no se da, se asigna el siguiente
    # Identificación / administrativo
    nif: Optional[str] = None
    descuento: Optional[float] = None
    # Contacto
    telefono_movil: Optional[str] = None   # WhatsApp / SMS → confirmación de citas
    telefono_fijo: Optional[str] = None
    telefono_fijo2: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    cp: Optional[str] = None
    # Responsable / tutor
    responsable_nombre: Optional[str] = None
    responsable_nif: Optional[str] = None
    responsable_parentesco: Optional[str] = None
    # Datos médicos
    grupo_sanguineo: Optional[str] = None
    peso: Optional[float] = None
    altura: Optional[float] = None
    medico_cabecera: Optional[str] = None
    tel_medico: Optional[str] = None
    especialista: Optional[str] = None
    # Consentimientos RGPD
    acepta_lopd: Optional[bool] = None
    acepta_info: Optional[bool] = None
    acepta_whatsapp: Optional[bool] = None
    acepta_bots: Optional[bool] = None
    # Notas internas
    notas: Optional[str] = None


# Campos de filiación (columnas directas) que se copian al Paciente en el alta.
_CAMPOS_FILIACION = (
    "nif", "descuento", "telefono_movil", "telefono_fijo", "telefono_fijo2", "email",
    "direccion", "cp", "responsable_nombre", "responsable_nif", "responsable_parentesco",
    "grupo_sanguineo", "peso", "altura", "medico_cabecera", "tel_medico", "especialista",
    "acepta_lopd", "acepta_info", "acepta_whatsapp", "acepta_bots", "notas",
)


def _siguiente_num_historia(session: Session, centro_id: int) -> str:
    nums = session.exec(select(Paciente.num_historia).where(
        Paciente.centro_id == centro_id, Paciente.num_historia.is_not(None))).all()
    maximo = 0
    for n in nums:
        try:
            maximo = max(maximo, int(str(n)))
        except (TypeError, ValueError):
            continue
    return str(maximo + 1)


def _crear_carpeta_drive_bg(paciente_id: int, centro_id: int) -> None:
    """Crea la carpeta del paciente en Drive DESPUÉS de responder el alta. Best-effort: si falla,
    el alta no se ve afectada y la carpeta se crea al subirse la primera imagen/RX."""
    try:
        from application.services.multimedia_service import MultimediaService
        with Session(engine) as s:
            pac = s.get(Paciente, paciente_id)
            if pac:
                MultimediaService(s).crear_carpeta_drive(centro_id, pac)
    except Exception:  # noqa: BLE001  # raiz: carpeta Drive best-effort, no afecta al alta
        pass


@router.post("/pacientes/nuevo", status_code=status.HTTP_201_CREATED)
def crear_paciente(datos: PacienteNuevoIn, background: BackgroundTasks,
                   centro_id: int = Depends(get_current_centro),
                   _user: CurrentUser = Depends(require_permission("pacientes.editar")),
                   session: Session = Depends(get_session)) -> dict:
    """Crea un paciente en la web y lo encola para sincronizar con Romexis (mismo NumPac/nombre/fecha)."""
    if not datos.nombre.strip() or not datos.apellidos.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nombre y apellidos obligatorios")
    nh = (datos.num_historia or "").strip() or _siguiente_num_historia(session, centro_id)
    if session.exec(select(Paciente).where(Paciente.centro_id == centro_id,
                                           Paciente.num_historia == nh)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe un paciente con Nº historia {nh}")
    pac = Paciente(centro_id=centro_id, num_historia=nh, nombre=datos.nombre.strip(),
                   apellidos=datos.apellidos.strip(), fecha_nacimiento=datos.fecha_nacimiento, activo=True)
    # Resto de filiación (columnas directas): se aplican solo los campos enviados.
    for campo in _CAMPOS_FILIACION:
        val = getattr(datos, campo, None)
        if val is None:
            continue
        setattr(pac, campo, val.strip() or None if isinstance(val, str) else val)
    session.add(pac)
    session.commit()
    session.refresh(pac)
    sync = _encolar(session, pac)
    background.add_task(_crear_carpeta_drive_bg, pac.id, centro_id)   # Drive: carpeta + RX + Imágenes
    return {"id": pac.id, "num_historia": nh, "romexis_sync_id": sync.id}


# ───────────────────────── endpoints del AGENTE (PC Romexis) ─────────────────────────
@router.get("/integraciones/romexis/pendientes", dependencies=[Depends(_internal_auth)])
def pendientes(session: Session = Depends(get_session)) -> dict:
    """Trabajos que el agente debe ejecutar en Romexis (crear/abrir/modificar)."""
    filas = session.exec(select(RomexisSync).where(RomexisSync.estado.in_(_ESTADOS_AGENTE))
                         .order_by(RomexisSync.created_at)).all()
    return {"pendientes": [{
        "id": s.id, "accion": "modificar" if s.estado == "modificar" else "sync",
        "num_historia": s.num_historia, "apellidos": s.apellidos, "nombre": s.nombre,
        "fecha_nacimiento": _fecha_iso(s.fecha_nacimiento),   # ISO; el agente la reformatea
    } for s in filas]}


class ResultadoIn(BaseModel):
    estado: str                          # creado | abierto | conflicto_id | resuelto | error
    romexis_apellidos: Optional[str] = None
    romexis_nombre: Optional[str] = None
    detalle: Optional[str] = None


@router.post("/integraciones/romexis/{sync_id}/resultado", dependencies=[Depends(_internal_auth)])
def resultado(sync_id: int, datos: ResultadoIn, session: Session = Depends(get_session)) -> dict:
    """El agente reporta el resultado de un trabajo."""
    valido = {"creado", "abierto", "conflicto_id", "resuelto", "error"}
    if datos.estado not in valido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Estado no válido")
    s = session.get(RomexisSync, sync_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabajo no encontrado")
    s.estado = datos.estado
    s.romexis_apellidos = datos.romexis_apellidos
    s.romexis_nombre = datos.romexis_nombre
    s.detalle = datos.detalle
    s.intentos = (s.intentos or 0) + 1
    session.add(s)
    session.commit()
    return {"ok": True, "estado": s.estado}


# ───────────────────────── endpoints de la WEB (resolver conflicto) ─────────────────────────
def _dto(s: RomexisSync) -> dict:
    return {"id": s.id, "paciente_id": s.paciente_id, "num_historia": s.num_historia,
            "apellidos": s.apellidos, "nombre": s.nombre, "estado": s.estado,
            "romexis_apellidos": s.romexis_apellidos, "romexis_nombre": s.romexis_nombre,
            "detalle": s.detalle}


@router.get("/romexis-sync")
def listar_sync(estado: Optional[str] = None, centro_id: int = Depends(get_current_centro),
                _user: CurrentUser = Depends(require_permission("pacientes.ver")),
                session: Session = Depends(get_session)) -> dict:
    """Estado del puente para el centro (para mostrar conflictos pendientes de decidir)."""
    q = select(RomexisSync).where(RomexisSync.centro_id == centro_id)
    if estado:
        q = q.where(RomexisSync.estado == estado)
    filas = session.exec(q.order_by(RomexisSync.created_at.desc())).all()
    return {"sync": [_dto(s) for s in filas]}


class ResolverIn(BaseModel):
    accion: str   # "modificar" (cambiar nombre en Romexis) | "nuevo_circuito" (revisión: id reutilizado)


@router.post("/romexis-sync/{sync_id}/resolver")
def resolver(sync_id: int, datos: ResolverIn, centro_id: int = Depends(get_current_centro),
             _user: CurrentUser = Depends(require_permission("pacientes.editar")),
             session: Session = Depends(get_session)) -> dict:
    """Resuelve un conflicto de ID: modificar el nombre en Romexis, o abrir nuevo circuito."""
    s = session.get(RomexisSync, sync_id)
    if not s or s.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabajo no encontrado")
    if s.estado != "conflicto_id":
        raise HTTPException(status.HTTP_409_CONFLICT, "El trabajo no está en conflicto")
    if datos.accion == "modificar":
        s.estado = "modificar"          # el agente lo recogerá y cambiará el nombre en Romexis
    elif datos.accion == "nuevo_circuito":
        s.estado = "nuevo_circuito"     # ese id pudo asignarse a otro paciente → revisión manual
        s.detalle = "Rechazado: el ID puede pertenecer a otro paciente en Romexis. Revisión manual."
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Acción no válida")
    session.add(s)
    session.commit()
    return {"ok": True, "estado": s.estado}
