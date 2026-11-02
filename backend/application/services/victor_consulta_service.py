"""VICTOR — la parte de consulta (escuchar y extraer el SOAP).

Su parcela (ver `domain/config/agentes.py`): lo que sucede en el gabinete, ADEMÁS de la
agenda/informes que ya llevaba (`victor_service.py`/`victor_agente.py`). Escucha la sesión,
la transcribe y extrae el SOAP para que el doctor no tenga que teclearlo. Se ciñe al
paciente que se está atendiendo. No habla con nadie por WhatsApp (eso es Alex) ni administra
el sistema (eso es Aura, ahora reservada a SuperUser).

Regla que gobierna todo lo de aquí: **Victor propone, el doctor dispone.** La transcripción
y el SOAP se guardan como borrador; nada entra en la historia clínica sin que una persona lo
revise y lo confirme.

Resiliencia: si el motor de voz principal falla, se intenta el de respaldo antes de darse
por vencida. Es la lección del modelo retirado por NVIDIA, que dejó la IA muda sin aviso
porque dependía de un único proveedor.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlmodel import Session, select

from application.services.llm_config import resolver_llm
from domain.models.config import Integracion
from domain.models.core import Cita, Paciente, Tratamiento
from domain.models.ia import Transcripcion as TranscripcionDB
from infrastructure.external_apis.llm_client import LLMClient, LLMError
from infrastructure.external_apis.stt_client import STTError, construir_motor

log = logging.getLogger("victor")

SOAP_SYSTEM = (
    "Eres Victor, el asistente de la clínica dental. Recibes la TRANSCRIPCIÓN de una "
    "consulta real entre doctor y paciente y la conviertes en una nota SOAP.\n\n"
    "Devuelve SOLO un JSON con estas cuatro claves, en español y en la lengua del doctor:\n"
    '  {"subjetivo": "...", "objetivo": "...", "analisis": "...", "plan": "..."}\n\n'
    "  · subjetivo → lo que CUENTA el paciente: motivo, síntomas, desde cuándo, qué le alivia.\n"
    "  · objetivo  → lo que VE el doctor: exploración, hallazgos, piezas afectadas, pruebas.\n"
    "  · analisis  → el diagnóstico o juicio clínico.\n"
    "  · plan      → qué se va a hacer: tratamiento, pruebas, prescripción, próxima cita.\n\n"
    "REGLAS DURAS: (1) No inventes NADA que no esté en la transcripción; si un apartado no "
    "se ha hablado, déjalo vacío (\"\"). (2) No añadas diagnósticos que el doctor no haya "
    "dicho. (3) Usa la nomenclatura dental que oigas (si dicen «pieza cuatro seis», escribe "
    "4.6). (4) Sé conciso: son notas clínicas, no un relato."
)


class VictorConsultaService:
    def __init__(self, session: Session, centro_id: int):
        self.s = session
        self.centro_id = centro_id

    # ───────────────────────── motores de voz ─────────────────────────
    def _cfg_stt(self, proveedor: Optional[str] = None) -> Optional[dict]:
        filas = self.s.exec(select(Integracion).where(
            Integracion.centro_id == self.centro_id, Integracion.tipo == "stt",
            Integracion.activo == True)).all()  # noqa: E712
        if proveedor:
            for i in filas:
                if (i.config or {}).get("proveedor") == proveedor:
                    return i.config
            return None
        return filas[0].config if filas else None

    def _permitida(self) -> tuple[bool, Optional[str]]:
        """¿Victor está activo? Sin esto no hay consulta que escuchar."""
        from application.services.agentes_config import estado as estado_agentes
        for e in estado_agentes(self.s, self.centro_id):
            if e["id"] == "victor":
                if not e["activa"]:
                    return False, "Victor está desactivado."
                if not e["operativa"]:
                    return False, f"Victor depende de {e['bloqueadoPor']}, que está desactivado."
                return True, None
        return True, None

    def estado(self) -> dict:
        """¿Puede Victor escuchar ahora mismo? Se comprueba de verdad contra el proveedor."""
        permitida, motivo_dep = self._permitida()
        cfg = self._cfg_stt()
        if not cfg:
            return {"ok": False, "motivo": "Sin motor de voz configurado", "motor": None,
                    "enviaFuera": None}
        motor = construir_motor(cfg)
        ok, motivo = motor.disponible()
        if not permitida:
            # El motor puede estar perfecto: lo que no está es la autorización para usarlo.
            return {"ok": False, "motivo": motivo_dep, "motor": motor.nombre,
                    "enviaFuera": motor.envia_fuera, "motorOk": ok}
        return {"ok": ok, "motivo": motivo, "motor": motor.nombre,
                # Que el audio salga de la clínica se DICE, no se esconde: es dato de salud.
                "enviaFuera": motor.envia_fuera}

    # ───────────────────────── vocabulario del gabinete ─────────────────────────
    def _contexto(self, paciente_id: Optional[int]) -> str:
        """Términos propios para orientar al motor de voz: donde más falla Whisper es en la
        jerga (nombres de tratamientos, apellidos). Darle el vocabulario sube el acierto."""
        piezas = "piezas dentales 1.1 a 4.8"
        ttos = [t.nombre for t in self.s.exec(
            select(Tratamiento).where(Tratamiento.centro_id == self.centro_id).limit(60)) if t.nombre]
        quien = ""
        if paciente_id and (p := self.s.get(Paciente, paciente_id)):
            quien = f"paciente {p.nombre or ''} {p.apellidos or ''}. "
        return f"{quien}Consulta dental. {piezas}. Tratamientos: {', '.join(ttos[:40])}"

    # ───────────────────────── escuchar ─────────────────────────
    def escuchar(self, audio: bytes, *, cita_id: int, paciente_id: int,
                 nombre_archivo: str = "consulta.wav") -> dict:
        """Transcribe la consulta y extrae el SOAP. Guarda como BORRADOR."""
        pac = self.s.get(Paciente, paciente_id)
        if not pac or pac.centro_id != self.centro_id:
            return {"ok": False, "motivo": "Paciente no encontrado"}
        cita = self.s.get(Cita, cita_id)
        if not cita or cita.centro_id != self.centro_id or cita.paciente_id != paciente_id:
            return {"ok": False, "motivo": "Cita no encontrada"}
        permitida, motivo_dep = self._permitida()
        if not permitida:
            return {"ok": False, "motivo": motivo_dep}
        cfg = self._cfg_stt()
        if not cfg:
            return {"ok": False, "motivo": "Victor no tiene motor de voz configurado."}

        contexto = self._contexto(paciente_id)
        intentos, tr = [], None
        # Principal primero; si cae, el respaldo. Nunca se rinde al primer fallo.
        for prov in (cfg.get("proveedor", "groq"), "gemini"):
            c = self._cfg_stt(prov) if prov != cfg.get("proveedor") else cfg
            if not c:
                continue
            motor = construir_motor(c)
            try:
                tr = motor.transcribir(audio, nombre_archivo=nombre_archivo, contexto=contexto)
                break
            except STTError as e:
                intentos.append(f"{motor.nombre}: {e}")
                log.warning("Victor · motor de voz falló (%s), probando respaldo", motor.nombre)
        if not tr:
            return {"ok": False, "motivo": "Ningún motor de voz pudo transcribir.",
                    "intentos": intentos}

        soap, aviso = self._extraer_soap(tr.texto)
        fila = TranscripcionDB(cita_id=cita_id, paciente_id=paciente_id,
                               texto=tr.texto[:20000],
                               extraido_json=json.dumps(soap, ensure_ascii=False)[:8000] if soap else None)
        self.s.add(fila); self.s.commit(); self.s.refresh(fila)
        return {"ok": True, "transcripcionId": fila.id, "motor": tr.motor,
                "duracionSeg": tr.duracion_seg, "texto": tr.texto,
                "soap": soap, "avisoSoap": aviso,
                "borrador": True,   # nada entra en la historia sin que el doctor lo confirme
                "intentosFallidos": intentos or None}

    # ───────────────────────── transcripción → SOAP ─────────────────────────
    def _extraer_soap(self, texto: str) -> tuple[Optional[dict], Optional[str]]:
        if not (texto or "").strip():
            return None, "La transcripción vino vacía."
        cfg = resolver_llm(self.s, self.centro_id, "victor")
        if not cfg:
            return None, "Sin modelo de texto configurado: queda la transcripción sin SOAP."
        try:
            msg = LLMClient(cfg).chat(
                [{"role": "system", "content": SOAP_SYSTEM},
                 {"role": "user", "content": texto[:12000]}],
                temperature=0.1, max_tokens=900)
        except LLMError as e:
            return None, f"El modelo no respondió: {e}"
        crudo = (msg.get("content") or "").strip()
        # Los modelos envuelven el JSON en ```json … ``` con frecuencia.
        if "```" in crudo:
            crudo = crudo.split("```")[1].removeprefix("json").strip()
        try:
            d = json.loads(crudo)
        except json.JSONDecodeError:
            return None, "El modelo no devolvió un SOAP legible."
        return {k: (d.get(k) or "").strip() for k in ("subjetivo", "objetivo", "analisis", "plan")}, None
