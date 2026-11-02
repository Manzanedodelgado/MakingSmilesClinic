"""Reglas de una cita de agenda — una sola fuente para todos los que crean o mueven citas
(pantalla de agenda, Jarvis, integraciones). Antes vivían solo en la pantalla
(`frontend/src/app/(app)/agenda/page.tsx` → noDisponible, docDeGab, duración por doctor+tipo)
y quien llamaba a la API directamente se las saltaba (citas 49004/49005 del 11-oct-2026).

Reglas:
  1. Obligatorios (regla de jmd, 11-oct-2026): fecha, hora, duración, tipo de cita, nombre,
     apellidos, teléfono y gabinete (sin gabinete la agenda la pinta en una columna
     "Sin gabinete" que no existe: cita 49005). Con ficha (paciente_id) nombre/apellidos/teléfono/num_historia
     salen de la ficha si no vienen.
  2. Catálogos: tipo, gabinete, doctor, agenda y estado deben existir en el centro.
  3. Disponibilidad (igual que la pantalla): ni festivo, ni día cerrado, ni fuera de los
     turnos del centro, ni franja bloqueada.
  4. Gabinete ↔ doctor: cada gabinete tiene, cada día, el doctor de su horario
     (colaborador_horarios). Si el gabinete tiene doctor asignado a esa hora, la cita es de
     ese doctor; lo que falte de los dos se completa desde el horario.
  5. Duración: si no viene, la configurada para ese doctor y tipo
     (Config → Colaboradores → "Tiempos por tipo de cita").
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, select

from application.services.config_service import ConfigService
from domain.models.agenda import Agenda, BloqueoAgenda, ColaboradorHorario, EstadoCita, Gabinete, TipoCita
from domain.models.core import ColaboradorTipoCita, Paciente
from domain.services.disponibilidad import a_min

_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _no(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)


def _vacio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _del_centro(session: Session, modelo, id_: Optional[int], centro_id: int):
    if id_ is None:
        return None
    obj = session.get(modelo, id_)
    if not obj or getattr(obj, "centro_id", None) != centro_id:
        return False
    return obj


def no_disponible(session: Session, centro_id: int, fecha: date, hora: str,
                  gabinete_id: Optional[int]) -> Optional[str]:
    """Mismo criterio que `noDisponible` de la pantalla de agenda."""
    cfg = ConfigService(session)
    if fecha.isoformat() in (cfg.resolve("centro.festivos", centro_id=centro_id, default=[]) or []):
        return "Día festivo — la clínica no atiende ese día."
    dias = (cfg.resolve("centro.horario", centro_id=centro_id, default={}) or {}).get("dias") or []
    if dias:
        dia = dias[fecha.weekday()] if fecha.weekday() < len(dias) else None
        if not dia or not dia.get("abierto"):
            return "La clínica permanece cerrada ese día."
        m = a_min(hora)
        en_turno = any(dia.get(a) and dia.get(b) and a_min(dia[a]) <= m < a_min(dia[b])
                       for a, b in (("t1a", "t1b"), ("t2a", "t2b")))
        if not en_turno:
            return "Fuera del horario de apertura del centro."
    dt = datetime.combine(fecha, datetime.strptime(hora, "%H:%M").time())
    for b in session.exec(select(BloqueoAgenda).where(BloqueoAgenda.centro_id == centro_id)).all():
        if b.gabinete_id and gabinete_id and b.gabinete_id != gabinete_id:
            continue
        ini = b.fecha_inicio if isinstance(b.fecha_inicio, datetime) else datetime.combine(b.fecha_inicio, datetime.min.time())
        fin = b.fecha_fin if isinstance(b.fecha_fin, datetime) else datetime.combine(b.fecha_fin, datetime.max.time())
        if ini <= dt < fin:
            return f"Agenda bloqueada: {b.motivo}" if b.motivo else "Franja bloqueada en la agenda."
    return None


def gabinete_y_doctor(session: Session, centro_id: int, fecha: date, hora: str,
                      gabinete_id: Optional[int], colaborador_id: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    """Regla gabinete↔doctor del horario de ese día (colaborador_horarios)."""
    m = a_min(hora)
    hs = [h for h in session.exec(select(ColaboradorHorario).where(
              ColaboradorHorario.centro_id == centro_id, ColaboradorHorario.activo == True,  # noqa: E712
              ColaboradorHorario.dia_semana == fecha.weekday())).all()
          if h.hora_inicio and h.hora_fin and a_min(h.hora_inicio) <= m < a_min(h.hora_fin)]
    if gabinete_id is not None:
        docs = {h.colaborador_id for h in hs if h.gabinete_id == gabinete_id}
        if docs:
            if colaborador_id is None and len(docs) == 1:
                colaborador_id = next(iter(docs))
            elif colaborador_id is not None and colaborador_id not in docs:
                raise _no(f"Ese gabinete lo tiene asignado otro doctor el {_DIAS[fecha.weekday()]} a las {hora} "
                          "(horario de colaboradores).")
    elif colaborador_id is not None:
        gabs = {h.gabinete_id for h in hs if h.colaborador_id == colaborador_id and h.gabinete_id}
        if len(gabs) == 1:
            gabinete_id = next(iter(gabs))
    else:
        pares = {(h.gabinete_id, h.colaborador_id) for h in hs if h.gabinete_id}
        if len(pares) == 1:
            gabinete_id, colaborador_id = next(iter(pares))
    return gabinete_id, colaborador_id


def validar_y_completar(session: Session, centro_id: int, body: dict) -> dict:
    """Valida una cita completa (crear/editar) y completa lo que la web ya sabe. Lanza 422."""
    b = dict(body)
    if _vacio(b.get("hora")) or not _HORA.match(str(b["hora"])):
        raise _no("La hora es obligatoria (HH:MM).")
    if b.get("paciente_id") is not None:
        pac = _del_centro(session, Paciente, b["paciente_id"], centro_id)
        if not pac:
            raise _no("Paciente no encontrado")
        for campo, valor in (("nombre", pac.nombre), ("apellidos", pac.apellidos),
                             ("telefono_movil", pac.telefono_movil or pac.telefono_fijo), ("num_historia", pac.num_historia)):
            if _vacio(b.get(campo)) and not _vacio(valor):
                b[campo] = valor
    for modelo, campo, nombre in ((TipoCita, "tipo_cita_id", "Tipo de cita"), (Gabinete, "gabinete_id", "Gabinete"),
                                  (Agenda, "agenda_id", "Agenda"), (EstadoCita, "estado_id", "Estado")):
        if _del_centro(session, modelo, b.get(campo), centro_id) is False:
            raise _no(f"{nombre} no encontrado en el centro")
    if b.get("colaborador_id") is not None:
        from api.colaborador_helper import colaboradores_activos_rows
        if b["colaborador_id"] not in {c.id for c, _u, _p in colaboradores_activos_rows(session, centro_id)}:
            raise _no("Doctor no encontrado en el centro")
    motivo = no_disponible(session, centro_id, b["fecha"], b["hora"], b.get("gabinete_id"))
    if motivo:
        raise _no(f"No se puede crear cita aquí: {motivo}")
    b["gabinete_id"], b["colaborador_id"] = gabinete_y_doctor(
        session, centro_id, b["fecha"], b["hora"], b.get("gabinete_id"), b.get("colaborador_id"))
    if b.get("duracion_min") is None and b.get("colaborador_id") and b.get("tipo_cita_id"):
        d = session.get(ColaboradorTipoCita, (b["colaborador_id"], b["tipo_cita_id"]))
        if d and d.duracion_min:
            b["duracion_min"] = d.duracion_min
    faltan = [n for c, n in (("gabinete_id", "gabinete"), ("duracion_min", "duración"), ("tipo_cita_id", "tipo de cita"), ("nombre", "nombre"),
                             ("apellidos", "apellidos"), ("telefono_movil", "teléfono")) if _vacio(b.get(c))]
    if faltan:
        raise _no("Faltan datos obligatorios de la cita: " + ", ".join(faltan) + ".")
    return b


def validar_movimiento(session: Session, centro_id: int, fecha: date, hora: str,
                       gabinete_id: Optional[int], colaborador_id: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    """Mover: disponibilidad + gabinete↔doctor (no exige los datos obligatorios a citas antiguas)."""
    if not _HORA.match(str(hora or "")):
        raise _no("La hora es obligatoria (HH:MM).")
    if gabinete_id is not None and _del_centro(session, Gabinete, gabinete_id, centro_id) is False:
        raise _no("Gabinete no encontrado en el centro")
    motivo = no_disponible(session, centro_id, fecha, hora, gabinete_id)
    if motivo:
        raise _no(f"No se puede mover la cita aquí: {motivo}")
    return gabinete_y_doctor(session, centro_id, fecha, hora, gabinete_id, colaborador_id)


# ─────────────── Infranqueable: las reglas se aplican en CADA guardado de una cita ───────────────
# Da igual quién guarde la cita (agenda, app del paciente, Alex, Escucha Activa, scripts o código
# futuro): al hacer INSERT, o UPDATE de un campo de la regla, se ejecutan estas mismas reglas y,
# si no se cumplen, la cita no se guarda. Un cambio solo de estado (p. ej. anular) no se bloquea.
from sqlalchemy import event, inspect as _sa_inspect, text  # noqa: E402

from domain.models._base import utcnow  # noqa: E402
from domain.models.core import Cita  # noqa: E402

_CAMPOS_CITA = ("fecha", "hora", "duracion_min", "agenda_id", "gabinete_id", "colaborador_id", "estado_id",
                "tipo_cita_id", "paciente_id", "nombre", "apellidos", "telefono_movil", "num_historia")
_CAMPOS_REGLA = set(_CAMPOS_CITA) - {"estado_id", "num_historia"}


def _aplicar_reglas(connection, cita: Cita) -> None:
    with Session(bind=connection) as s:
        cuerpo = validar_y_completar(s, cita.centro_id, {k: getattr(cita, k) for k in _CAMPOS_CITA})
    for k, v in cuerpo.items():
        if getattr(cita, k) != v:
            setattr(cita, k, v)


# ── Identidad de la cita (regla de jmd, 12-oct-2026) ───────────────────────────────────────
# `id_cita` (hilo lógico heredado de Getite) nace UNA vez con la cita y no cambia nunca:
# moverla, reprogramarla o cambiarle el estado no toca el hilo. Copiar una cita de estado
# final (finalizada, cancelada, anulada) —lo que hace el personal para abrir la nueva que
# pide el paciente— es una cita NUEVA: si la fila trae un id_cita que ya existe en la tabla,
# es una copia y se le asigna otro. Igual que las reglas de arriba, vale para quien guarde la
# cita (agenda, app del paciente, Jarvis o SQL directo con la migración 039 aplicada).


def _id_cita_ya_usado(connection, id_cita: int) -> bool:
    fila = connection.execute(
        text("SELECT 1 FROM citas WHERE id_cita = :v LIMIT 1"), {"v": id_cita}).first()
    return fila is not None


def _nuevo_id_cita(connection) -> int:
    """Postgres: secuencia atómica (migración 039). Si la migración no está aplicada,
    nextval FALLA alto — un id_cita duplicado o un hilo perdido sería peor que un deploy
    parado, y callarlo aquí es exactamente lo que no hay que hacer. SQLite (tests):
    max+1 — con el ritmo de la clínica (una cita a cada vez) no llega a solaparse."""
    if connection.dialect.name == "postgresql":
        return connection.execute(text("SELECT nextval('citas_id_cita_seq')")).scalar()
    return connection.execute(
        text("SELECT COALESCE(MAX(id_cita), 0) + 1 FROM citas")).scalar()


def _sellar_identidad(connection, cita: Cita) -> None:
    """Nacimiento de la cita: sellos de creación/modificación e id_cita propio."""
    if cita.fecha_hora_creacion is None:
        cita.fecha_hora_creacion = utcnow()
    if cita.fecha_hora_modificacion is None:
        cita.fecha_hora_modificacion = cita.fecha_hora_creacion
    if cita.id_cita is None or _id_cita_ya_usado(connection, cita.id_cita):
        cita.id_cita = _nuevo_id_cita(connection)


@event.listens_for(Cita, "before_insert")
def _cita_antes_de_insertar(_mapper, connection, cita: Cita) -> None:
    _aplicar_reglas(connection, cita)
    _sellar_identidad(connection, cita)


@event.listens_for(Cita, "before_update")
def _cita_antes_de_actualizar(_mapper, connection, cita: Cita) -> None:
    estado = _sa_inspect(cita)
    # Identidad inmutable: si algo intenta reescribir id_cita o fecha_hora_creacion, se revierte.
    for campo in ("id_cita", "fecha_hora_creacion"):
        hist = estado.attrs[campo].history
        if hist.has_changes() and hist.deleted:
            setattr(cita, campo, hist.deleted[0])
    cita.fecha_hora_modificacion = utcnow()   # última modificación: se renueva en cada UPDATE
    if any(estado.attrs[k].history.has_changes() for k in _CAMPOS_REGLA):
        _aplicar_reglas(connection, cita)
