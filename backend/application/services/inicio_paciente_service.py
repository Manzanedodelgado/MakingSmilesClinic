"""INICIO · el paciente de agenda, entero, en una llamada.

Desde Inicio se gestiona todo lo del paciente que tiene cita: su Agenda (todas sus citas),
sus Automatizaciones (lo que Motion le ha enviado y lo que le enviaría ahora) y su Flujo de
WhatsApp (en qué paso de la máquina de estados está su conversación).

Cada sección respeta el permiso de su área: sin él devuelve {"permitido": False} y nada más.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from sqlmodel import Session, select

from application.services.automatizacion_service import AutomatizacionService, render
from application.services.automatizacion_triggers import (
    CATALOGO,
    CATALOGO_IDX,
    DEFAULTS,
    MAX_LOTE,
    TRIGGERS,
    Candidatos,
)
from domain.models.agenda import EstadoCita, Gabinete, TipoCita
from domain.models.comunicacion import Conversacion, EnvioAutomatico
from domain.models.core import Cita, Colaborador, Paciente
from domain.models.identidad import Usuario, UsuarioPeriodo
from domain.services import telefono as tel
from domain.services.whatsapp_flujos import FLUJOS_INFO

logger = logging.getLogger(__name__)

MAX_PASADAS = 20
MAX_ENVIADOS = 30
_FLUJO_NOMBRE = {f["id"]: f["nombre"] for f in FLUJOS_INFO}


class InicioPacienteService:
    def __init__(self, session: Session, centro_id: int, permisos: set[str]):
        self.s = session
        self.centro_id = centro_id
        self.p = permisos
        self.hoy = date.today()

    def _puede(self, *codigos: str) -> bool:
        return any(c in self.p for c in codigos)

    def resumen(self, pid: int) -> dict | None:
        """None si el paciente no existe en ESTE centro (el router responde 404)."""
        pac = self.s.get(Paciente, pid)
        if pac is None or pac.centro_id != self.centro_id:
            return None
        return {
            "pacienteId": pid,
            "citas": self._citas(pid),
            "automatizaciones": self._automatizaciones(pac),
            "flujo": self._flujo(pac),
        }

    # ─────────────────────────── AGENDA ───────────────────────────
    def _citas(self, pid: int) -> dict:
        if not self._puede("citas.ver"):
            return {"permitido": False}
        filas = self.s.exec(
            select(Cita, EstadoCita, TipoCita, Gabinete)
            .join(EstadoCita, EstadoCita.id == Cita.estado_id, isouter=True)
            .join(TipoCita, TipoCita.id == Cita.tipo_cita_id, isouter=True)
            .join(Gabinete, Gabinete.id == Cita.gabinete_id, isouter=True)
            .where(Cita.centro_id == self.centro_id, Cita.paciente_id == pid)
        ).all()
        # Anulada por CÓDIGO: los ids de estado cambian en cada centro/agenda.
        filas = [f for f in filas if not (f[1] and f[1].codigo == "anulada")]
        doctores = self._doctores({f[0].colaborador_id for f in filas})

        def dto(c: Cita, e: EstadoCita | None, t: TipoCita | None, g: Gabinete | None) -> dict:
            return {"id": c.id, "fecha": c.fecha.isoformat() if c.fecha else None,
                    "hora": (c.hora or "")[:5], "duracion": c.duracion_min,
                    "estado": e.nombre if e else "Planificada",
                    "estadoCodigo": e.codigo if e else None, "estadoId": c.estado_id,
                    "tipo": t.nombre if t else None, "tipoCitaId": c.tipo_cita_id,
                    "gabinete": g.nombre if g else None, "gabineteId": c.gabinete_id,
                    "doctor": doctores.get(c.colaborador_id), "colaboradorId": c.colaborador_id,
                    "agendaId": c.agenda_id}

        orden = lambda f: (f[0].fecha or date.min, f[0].hora or "")
        proximas = sorted((f for f in filas if f[0].fecha and f[0].fecha >= self.hoy), key=orden)
        pasadas = sorted((f for f in filas if not f[0].fecha or f[0].fecha < self.hoy),
                         key=orden, reverse=True)
        return {"permitido": True,
                "proximas": [dto(*f) for f in proximas],
                "pasadas": [dto(*f) for f in pasadas[:MAX_PASADAS]],
                "totalPasadas": len(pasadas)}

    def _doctores(self, ids: set[int | None]) -> dict[int, str]:
        limpio = [i for i in ids if i]
        if not limpio:
            return {}
        filas = self.s.exec(
            select(Colaborador.id, Usuario.nombre, Usuario.apellidos)
            .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
            .join(Usuario, Usuario.id == UsuarioPeriodo.usuario_id)
            .where(Colaborador.id.in_(limpio))).all()
        return {cid: f"{n or ''} {a or ''}".strip() for cid, n, a in filas}

    # ─────────────────────────── AUTOMATIZACIONES ───────────────────────────
    def _automatizaciones(self, pac: Paciente) -> dict:
        if not self._puede("comunicacion.ver"):
            return {"permitido": False}
        auto = AutomatizacionService(self.s)
        nombre = lambda d: CATALOGO_IDX.get(d, {}).get("nombre", d)
        enviados = self.s.exec(
            select(EnvioAutomatico)
            .where(EnvioAutomatico.centro_id == self.centro_id, EnvioAutomatico.paciente_id == pac.id)
            .order_by(EnvioAutomatico.fecha_envio.desc(), EnvioAutomatico.id.desc())  # type: ignore[union-attr]
            .limit(MAX_ENVIADOS)).all()
        try:
            pendientes = self._pendientes(auto, pac.id)
        except Exception:  # raiz: cálculo de automatizaciones pendientes falla -> lista vacía; el bloque no se cae
            logger.exception("inicio · automatizaciones pendientes del paciente %s", pac.id)
            pendientes = []
        try:
            maestro = auto.maestro(self.centro_id)
        except Exception:  # raiz: maestro de automatizaciones no disponible -> se trata como apagado (False)
            logger.exception("inicio · maestro automatizaciones centro %s", self.centro_id)
            maestro = False
        return {"permitido": True, "maestro": maestro,
                "enviados": [{"disparador": e.disparador, "nombre": nombre(e.disparador),
                              "fecha": e.fecha_envio.isoformat(), "canal": e.canal}
                             for e in enviados],
                "pendientes": [{**p, "nombre": nombre(p["disparador"])} for p in pendientes]}

    def _pendientes(self, auto: AutomatizacionService, pid: int) -> list[dict]:
        """Lo que Motion le enviaría a ESTE paciente si corriera ahora (reglas encendidas,
        sin repetir lo ya enviado). Mismo criterio que el preview de Motion, sin enviar nada."""
        buscador = Candidatos(self.s, self.centro_id, paciente_id=pid)
        out: list[dict] = []
        for c in CATALOGO:
            d = c["disparador"]
            fila = auto._fila(self.centro_id, d)
            if not (fila and fila.activo):
                continue
            plantilla = fila.cuerpo or DEFAULTS.get(d, "")
            for cand in TRIGGERS[d](buscador)[: MAX_LOTE.get(d, 200)]:
                if cand.get("paciente_id") != pid or auto._ya_enviado(self.centro_id, d, cand["clave"]):
                    continue
                out.append({"disparador": d, "mensaje": render(plantilla, cand["vars"])})
        return out

    # ─────────────────────────── FLUJO WHATSAPP ───────────────────────────
    def _flujo(self, pac: Paciente) -> dict:
        if not self._puede("comunicacion.ver"):
            return {"permitido": False}
        return {"permitido": True, "conversacion": self._conversacion(pac.id, pac.telefono_movil)}

    def conversacion(self, pid: int | None, telefono: str | None) -> dict:
        """La conversación de WhatsApp del paciente de agenda, tenga ficha o no (citas dadas sin
        vincular: solo hay teléfono). Si hay ficha, manda su móvil; el de la cita es el respaldo."""
        if not self._puede("comunicacion.ver"):
            return {"permitido": False}
        pac = self.s.get(Paciente, pid) if pid else None
        if pac is not None and pac.centro_id != self.centro_id:
            pac = None
        movil = (pac.telefono_movil if pac and pac.telefono_movil else None) or telefono
        return {"permitido": True,
                "aceptaBots": (pac.acepta_bots if pac is not None else None),
                "telefono": tel.normalizar(movil) if movil else None,
                "conversacion": self._conversacion(pac.id if pac else None, movil)}

    def _conversacion(self, pid: int | None, telefono: str | None) -> dict | None:
        movil = tel.normalizar(telefono) if telefono else None
        conds = []
        if pid:
            conds.append(Conversacion.paciente_id == pid)
        if movil:
            conds.append(Conversacion.telefono == movil)
        if not conds:
            return None
        cond = conds[0] if len(conds) == 1 else (conds[0] | conds[1])
        conv = self.s.exec(
            select(Conversacion)
            .where(Conversacion.centro_id == self.centro_id, Conversacion.canal == "whatsapp", cond)
            .order_by(Conversacion.ultimo_mensaje_at.desc())  # type: ignore[union-attr]
        ).first()
        if conv is None:
            return None
        est = conv.estado_flujo if isinstance(conv.estado_flujo, dict) else None
        intent = est.get("intent") if est else None
        pausa = conv.ia_pausada_hasta
        return {
            "id": conv.id, "telefono": conv.telefono, "noLeidos": conv.no_leidos,
            "estado": conv.estado,
            "flujo": None if not est else {
                "id": intent, "nombre": _FLUJO_NOMBRE.get(intent, intent), "paso": est.get("paso")},
            "iaPausada": bool(pausa and pausa > datetime.now()),
            "iaPausadaHasta": pausa.isoformat() if pausa else None,
        }
