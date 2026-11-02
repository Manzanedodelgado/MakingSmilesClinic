"""Disponibilidad de agenda (capa de aplicación). Carga horarios/citas/bloqueos de la
BBDD nueva y delega el cálculo de huecos en el dominio puro (disponibilidad.py)."""
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from domain.models.agenda import BloqueoAgenda, ColaboradorHorario, EstadoCita
from domain.models.core import Cita, Colaborador
from domain.services import disponibilidad as dom

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _label(d: date) -> str:
    return f"{DIAS_ES[d.weekday()]} {d.day} de {MESES_ES[d.month]}"


def estado_id_por_codigo(session: Session, centro_id: int, codigo: str,
                         agenda_id: Optional[int] = None) -> Optional[int]:
    """Resuelve el id de un estado_cita por su código semántico. estados_cita.id es un
    autoincremental GLOBAL (no por centro): el mismo código ('anulada', 'planificada')
    tiene un id distinto en cada centro. NUNCA hardcodear el número — único punto de
    resolución, reutilizado por agenda_router.py y aquí (huecos de personal Y de paciente)."""
    stmt = select(EstadoCita).where(EstadoCita.centro_id == centro_id, EstadoCita.codigo == codigo)
    if agenda_id:
        con_agenda = session.exec(stmt.where(EstadoCita.agenda_id == agenda_id)).first()
        if con_agenda:
            return con_agenda.id
    row = session.exec(stmt).first()
    return row.id if row else None


class DisponibilidadService:
    def __init__(self, session: Session):
        self.session = session

    def huecos(self, centro_id: int, *, agenda_id: Optional[int] = None,
               colaborador_id: Optional[int] = None, dias: int = 7,
               duracion_min: int = 30, max_huecos: int = 12) -> list[dict]:
        hoy = date.today()
        fin = hoy + timedelta(days=dias)

        # Horarios de trabajo
        q_h = select(ColaboradorHorario).where(
            ColaboradorHorario.centro_id == centro_id, ColaboradorHorario.activo == True)  # noqa: E712
        if agenda_id:
            q_h = q_h.where(ColaboradorHorario.agenda_id == agenda_id)
        if colaborador_id:
            q_h = q_h.where(ColaboradorHorario.colaborador_id == colaborador_id)
        horarios = [dom.Horario(
            colaborador_id=h.colaborador_id, gabinete_id=h.gabinete_id, dia_semana=h.dia_semana,
            hora_inicio=h.hora_inicio, hora_fin=h.hora_fin,
            pausa_inicio=h.pausa_inicio, pausa_fin=h.pausa_fin)
            for h in self.session.exec(q_h).all()]
        if not horarios:
            return []

        # Citas que ocupan (no anuladas — resuelto por código, no por id hardcodeado)
        anulada_id = estado_id_por_codigo(self.session, centro_id, "anulada", agenda_id)
        q_c = select(Cita).where(
            Cita.centro_id == centro_id, Cita.fecha > hoy, Cita.fecha <= fin,
            Cita.hora.isnot(None), Cita.colaborador_id.isnot(None))  # type: ignore[union-attr]
        if colaborador_id:
            q_c = q_c.where(Cita.colaborador_id == colaborador_id)
        ocup = [dom.Ocupacion(colaborador_id=c.colaborador_id, fecha=c.fecha, hora=c.hora,
                              duracion_min=c.duracion_min or duracion_min)
                for c in self.session.exec(q_c).all() if c.estado_id != anulada_id]

        # Bloqueos en rango
        bloqueos = [dom.Bloqueo(fecha_inicio=b.fecha_inicio, fecha_fin=b.fecha_fin,
                                colaborador_id=b.colaborador_id)
                    for b in self.session.exec(select(BloqueoAgenda).where(
                        BloqueoAgenda.centro_id == centro_id,
                        BloqueoAgenda.fecha_fin >= hoy)).all()]

        # Ausencias del colaborador (Config → Colaboradores) → bloquean su disponibilidad como un
        # bloqueo más, en sus fechas. Se limita a los colaboradores que ya tienen horario en scope.
        col_ids = {h.colaborador_id for h in horarios if h.colaborador_id is not None}
        if col_ids:
            ausentes = self.session.exec(select(Colaborador).where(
                Colaborador.id.in_(col_ids),                                    # type: ignore[attr-defined]
                Colaborador.ausencia_inicio.isnot(None),                        # type: ignore[union-attr]
                Colaborador.ausencia_fin.isnot(None),                           # type: ignore[union-attr]
                Colaborador.ausencia_fin >= hoy)).all()
            bloqueos += [dom.Bloqueo(fecha_inicio=c.ausencia_inicio, fecha_fin=c.ausencia_fin,
                                     colaborador_id=c.id) for c in ausentes]

        huecos = dom.calcular_huecos(horarios, ocup, bloqueos, hoy=hoy, dias=dias,
                                     duracion_min=duracion_min, max_huecos=max_huecos)
        return [{"fecha": h.fecha.isoformat(), "etiqueta": _label(h.fecha), "hora": h.hora,
                 "colaboradorId": h.colaborador_id, "gabineteId": h.gabinete_id}
                for h in huecos]
