"""Voicebot (capa de aplicación). Port de voicebot.service/controller (.37).

El canal de voz reutiliza el agente Alex: una pasarela telefónica (Asterisk/AGI,
Twilio, Zadarma…) transcribe lo que dice el paciente y manda el turno aquí; el
agente responde en 1-2 frases (para TTS) y la llamada se registra para historial y
métricas. La config SIP vive en `integraciones` tipo='voicebot_sip' (CanalesIA); el
on/off del canal en `configuraciones` `agente.alex.canales.voicebot` (AgentesIA).
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlmodel import Session, select

from application.services.config_service import ConfigService
from domain.models.comunicacion import LlamadaVoz
from domain.models.config import Integracion
from domain.models.core import Centro, Paciente
from infrastructure.external_apis.llm_client import LLMError

HANDOFF = "Ahora mismo no puedo atenderle por aquí. Le paso con el equipo, un momento por favor."


class VoicebotService:
    def __init__(self, session: Session):
        self.session = session

    def _alex(self, centro_id: int) -> dict:
        return ConfigService(self.session).for_scope(
            centro_id=centro_id, sistema="ia").get("agente.alex") or {}

    def _sip(self, centro_id: int) -> Optional[Integracion]:
        return self.session.exec(select(Integracion).where(
            Integracion.centro_id == centro_id, Integracion.tipo == "voicebot_sip")).first()

    def _canal_activo(self, centro_id: int) -> bool:
        return bool((self._alex(centro_id).get("canales") or {}).get("voicebot"))

    # ─────────────────────── CONFIG / HEALTH (para el AGI) ───────────────────────
    def voice_config(self, centro_id: int) -> dict:
        alex = self._alex(centro_id)
        persona = alex.get("persona") or {}
        voz = alex.get("voz") or {}
        centro = self.session.get(Centro, centro_id)
        return {
            "agente": persona.get("nombre") or "Alex",
            "bienvenida": persona.get("bienvenida") or "Hola, ha llamado a la clínica. ¿En qué puedo ayudarle?",
            "despedida": persona.get("despedida") or "Gracias por su llamada. Hasta pronto.",
            "clinica": centro.nombre if centro else "",
            # Voz para el TTS de la pasarela telefónica (acento + velocidad).
            "acento": voz.get("acento") or "es",
            "velocidad": voz.get("velocidad") or "normal",
            "canal_activo": self._canal_activo(centro_id),
        }

    def health(self, centro_id: int) -> dict:
        ig = self._sip(centro_id)
        cfg = (ig.config or {}) if ig else {}
        sip_ok = bool(cfg.get("host") and cfg.get("usuario"))
        return {"sip_configurado": sip_ok, "canal_activo": self._canal_activo(centro_id),
                "did": cfg.get("did")}

    # ─────────────────────── PROCESAR UN TURNO DE VOZ ───────────────────────
    def procesar_turno(self, centro_id: int, telefono: str, texto: str,
                       duracion_seg: Optional[int] = None) -> dict:
        """El AGI manda lo que dijo el paciente; devolvemos la respuesta (para TTS)."""
        if not self._canal_activo(centro_id):
            return {"respuesta": HANDOFF, "atendido": False, "motivo": "canal_inactivo"}
        respuesta, atendido = self._respuesta_agente(centro_id, telefono, texto)
        self._registrar(centro_id, telefono, texto, respuesta, duracion_seg, "finalizada")
        return {"respuesta": respuesta, "atendido": atendido}

    def _respuesta_agente(self, centro_id: int, telefono: str, texto: str) -> tuple[str, bool]:
        from application.services.agente_service import AgenteService
        try:
            r = AgenteService(self.session).responder(centro_id, telefono, texto, enviar=False, voz=True)
            return r.get("respuesta") or HANDOFF, True
        except LLMError:
            return HANDOFF, False   # sin LLM configurado → handoff

    def _registrar(self, centro_id: int, telefono: str, entrada: str, respuesta: str,
                   duracion_seg: Optional[int], estado: str) -> None:
        pac = self._match_paciente(centro_id, telefono)
        self.session.add(LlamadaVoz(
            centro_id=centro_id, paciente_id=pac, telefono=telefono,
            entrada=(entrada or "")[:2000], respuesta=(respuesta or "")[:2000],
            duracion_seg=duracion_seg, estado=estado))
        self.session.commit()

    def _match_paciente(self, centro_id: int, telefono: str) -> Optional[int]:
        from domain.services import telefono as tel
        n9 = tel.ultimos9(telefono or "")
        if len(n9) < 9:
            return None
        row = self.session.execute(text("""
            SELECT id FROM pacientes WHERE centro_id = :c AND activo = TRUE AND (
                  right(regexp_replace(coalesce(telefono_movil,''),'\\D','','g'),9) = :n9
               OR right(regexp_replace(coalesce(telefono_fijo,''), '\\D','','g'),9) = :n9
               OR right(regexp_replace(coalesce(telefono_fijo2,''),'\\D','','g'),9) = :n9)
            ORDER BY id ASC LIMIT 1
        """), {"c": centro_id, "n9": n9}).first()
        return row[0] if row else None

    # ─────────────────────── HISTORIAL / MÉTRICAS ───────────────────────
    def historial(self, centro_id: int, paciente_id: Optional[int] = None, limit: int = 50) -> list[dict]:
        q = select(LlamadaVoz).where(LlamadaVoz.centro_id == centro_id)
        if paciente_id:
            q = q.where(LlamadaVoz.paciente_id == paciente_id)
        rows = self.session.exec(
            q.order_by(LlamadaVoz.created_at.desc()).limit(limit)).all()  # type: ignore[union-attr]
        return [{"id": r.id, "telefono": r.telefono, "entrada": r.entrada,
                 "respuesta": r.respuesta, "duracionSeg": r.duracion_seg, "estado": r.estado,
                 "fecha": r.created_at.isoformat() if r.created_at else None} for r in rows]

    def stats(self, centro_id: int, dias: int = 30) -> dict:
        desde = datetime.utcnow() - timedelta(days=dias)
        row = self.session.execute(text("""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE estado = 'finalizada') AS finalizadas,
                   coalesce(avg(duracion_seg), 0) AS dur_media
            FROM llamadas_voz WHERE centro_id = :c AND created_at >= :d
        """), {"c": centro_id, "d": desde}).first()
        return {"dias": dias, "total": int(row[0] or 0), "finalizadas": int(row[1] or 0),
                "duracionMediaSeg": round(float(row[2] or 0), 1)}
