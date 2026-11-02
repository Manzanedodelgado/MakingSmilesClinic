"""VICTOR — el agente que atiende al DOCTOR y al EQUIPO.

Su parcela (ver `domain/config/agentes.py`): peticiones de gestión del centro. Bloquear la
agenda de un doctor un día concreto, sacar un listado de pacientes que no vienen desde hace
más de un año, consultar qué hay hoy. Mira hacia dentro; con el paciente habla Alex.

Dos reglas que gobiernan este servicio:

  1. **Leer es directo; escribir se confirma.** Las herramientas que sólo consultan se
     ejecutan y ya. Las que cambian datos (bloquear una agenda) devuelven primero una
     PREVISUALIZACIÓN de lo que harían, y sólo se ejecutan cuando llega `confirmar=True`.
     Un agente no bloquea la agenda de nadie porque le haya parecido entender que sí.

  2. **Todo scopeado al centro.** Ninguna herramienta acepta un centro por parámetro: sale
     del token de quien pregunta.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlmodel import Session, func, select

from domain.models.agenda import BloqueoAgenda
from domain.models.core import Cita, Colaborador, ColaboradorCentro, Paciente
from domain.models.identidad import Usuario, UsuarioPeriodo

# El modelo no sabe qué día de la semana cae una fecha y, si la reescribe él, se equivoca
# (dijo "el lunes (20 de octubre)" cuando el lunes era el 19). Las herramientas devuelven la
# fecha ya escrita y el prompt le ordena copiarla tal cual (ver victor_agente, regla 5).
_DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre")


def fecha_en_texto(d: date) -> str:
    """2026-10-19 → 'lunes 19 de octubre de 2026'."""
    return f"{_DIAS_ES[d.weekday()]} {d.day} de {_MESES_ES[d.month - 1]} de {d.year}"



class VictorService:
    def __init__(self, session: Session, centro_id: int):
        self.s = session
        self.centro_id = centro_id

    # ───────────────────────── localizar al doctor ─────────────────────────
    def _colaborador(self, nombre: str) -> tuple[Optional[Colaborador], list[str]]:
        """Busca un colaborador ACTIVO por nombre. Devuelve (encontrado, candidatos).

        Sólo personal en activo: `fecha_baja IS NULL`. Un ex-colaborador no tiene agenda que
        bloquear, y contarlo sería el error que ya se ha cometido en otros listados."""
        t = (nombre or "").strip().lower()
        if not t:
            return None, []
        # El colaborador NO tiene centro_id: la identidad va por usuario_periodos y la
        # pertenencia al centro por la tabla puente colaborador_centro.
        filas = self.s.exec(select(Colaborador, Usuario)
                            .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
                            .join(Usuario, Usuario.id == UsuarioPeriodo.usuario_id)
                            .join(ColaboradorCentro, ColaboradorCentro.colaborador_id == Colaborador.id)
                            .where(ColaboradorCentro.centro_id == self.centro_id,
                                   UsuarioPeriodo.fecha_baja.is_(None))).all()
        cands = []
        for col, usu in filas:
            full = f"{usu.nombre or ''} {usu.apellidos or ''}".strip()
            if t in full.lower():
                cands.append((col, full))
        if len(cands) == 1:
            return cands[0][0], [cands[0][1]]
        return None, [c[1] for c in cands]

    # ───────────────────────── bloquear / liberar agenda ─────────────────────────
    def bloquear_agenda(self, doctor: str, fecha: str, *, motivo: str = "",
                        desde: Optional[str] = None, hasta: Optional[str] = None,
                        confirmar: bool = False) -> dict:
        """Bloquea la agenda de un doctor un día (o un tramo de ese día).

        Sin `confirmar` sólo describe lo que haría e informa de cuántas citas hay ya en ese
        rango: bloquear encima de citas existentes no las borra, y quien decide qué hacer
        con ellas es una persona."""
        col, cands = self._colaborador(doctor)
        if not col:
            return {"ok": False, "necesitaAclaracion": True,
                    "motivo": (f"No encuentro a ningún doctor en activo llamado «{doctor}»."
                               if not cands else
                               f"Hay varios que encajan con «{doctor}»: {', '.join(cands)}. ¿Cuál?"),
                    "candidatos": cands}
        try:
            dia = date.fromisoformat(fecha)
        except ValueError:
            return {"ok": False, "necesitaAclaracion": True,
                    "motivo": f"No entiendo la fecha «{fecha}». Necesito AAAA-MM-DD."}

        h_ini = time.fromisoformat(desde) if desde else time(0, 0)
        h_fin = time.fromisoformat(hasta) if hasta else time(23, 59)
        ini, fin = datetime.combine(dia, h_ini), datetime.combine(dia, h_fin)

        citas = self.s.exec(select(func.count(Cita.id)).where(
            Cita.centro_id == self.centro_id, Cita.colaborador_id == col.id,
            Cita.fecha == dia, Cita.estado_id != 1)).one() or 0   # 1 = Anulada

        nombre = cands[0] if cands else doctor
        rango = "todo el día" if not (desde or hasta) else f"de {h_ini:%H:%M} a {h_fin:%H:%M}"
        if not confirmar:
            return {"ok": True, "confirmado": False,
                    "resumen": f"Bloquear la agenda de {nombre} el {dia:%d/%m/%Y}, {rango}.",
                    "citasAfectadas": citas,
                    "aviso": (f"Ojo: ese día ya tiene {citas} cita(s). El bloqueo NO las borra; "
                              f"habrá que reubicarlas a mano.") if citas else None,
                    "paraEjecutar": "Vuelve a pedirlo con confirmar=true."}

        b = BloqueoAgenda(centro_id=self.centro_id, colaborador_id=col.id,
                          fecha_inicio=ini, fecha_fin=fin, motivo=(motivo or "Bloqueo")[:200])
        self.s.add(b); self.s.commit(); self.s.refresh(b)
        return {"ok": True, "confirmado": True, "bloqueoId": b.id,
                "resumen": f"Agenda de {nombre} bloqueada el {dia:%d/%m/%Y}, {rango}.",
                "citasAfectadas": citas}

    def liberar_agenda(self, bloqueo_id: int) -> dict:
        """Deshace un bloqueo. Sólo del propio centro."""
        b = self.s.get(BloqueoAgenda, bloqueo_id)
        if not b or b.centro_id != self.centro_id:
            return {"ok": False, "motivo": "Ese bloqueo no existe en este centro."}
        self.s.delete(b); self.s.commit()
        return {"ok": True, "resumen": f"Bloqueo {bloqueo_id} eliminado."}

    # ───────────────────────── informes ─────────────────────────
    def pacientes_sin_venir(self, meses: int = 12, limite: int = 200) -> dict:
        """Pacientes activos cuya última cita ASISTIDA es anterior a N meses (o ninguna).

        Se cuenta sobre citas realmente atendidas (estado Finalizada=5), no sobre citas
        planificadas: alguien que pidió cita y no vino no ha 'venido'."""
        corte = date.today() - timedelta(days=int(meses * 30.44))
        ultima = (select(Cita.paciente_id, func.max(Cita.fecha).label("ult"))
                  .where(Cita.centro_id == self.centro_id, Cita.estado_id == 5,
                         Cita.paciente_id.is_not(None))
                  .group_by(Cita.paciente_id)).subquery()
        filas = self.s.exec(
            select(Paciente, ultima.c.ult)
            .outerjoin(ultima, ultima.c.paciente_id == Paciente.id)
            .where(Paciente.centro_id == self.centro_id, Paciente.activo == True,  # noqa: E712
                   (ultima.c.ult < corte) | (ultima.c.ult.is_(None)))
            .order_by(ultima.c.ult.desc().nullslast())).all()
        total = len(filas)
        datos = [{"numHistoria": p.num_historia,
                   "paciente": f"{p.apellidos or ''}, {p.nombre or ''}".strip(", "),
                   "telefono": p.telefono_movil or p.telefono_fijo,
                   "ultimaVisita": ult.isoformat() if ult else None,
                   "enlace": f"/pacientes/{p.id}/ficha"}
                 for p, ult in filas[:limite]]
        return {"ok": True, "total": total, "mostrados": len(datos),
                "criterio": f"Sin visita atendida desde hace más de {meses} meses",
                "pacientes": datos}

    def resumen_dia(self, fecha: Optional[str] = None) -> dict:
        """Qué tiene el centro un día: citas por estado y quién trabaja."""
        dia = date.fromisoformat(fecha) if fecha else date.today()
        filas = self.s.exec(
            select(Cita.estado_id, func.count(Cita.id))
            .where(Cita.centro_id == self.centro_id, Cita.fecha == dia)
            .group_by(Cita.estado_id)).all()
        from domain.models.agenda import EstadoCita
        nombres = {e.id: e.nombre for e in self.s.exec(select(EstadoCita))}
        return {"ok": True, "fecha": dia.isoformat(), "fechaTexto": fecha_en_texto(dia),
                "total": sum(n for _, n in filas),
                "porEstado": [{"estado": nombres.get(eid, str(eid)), "n": n} for eid, n in filas]}
