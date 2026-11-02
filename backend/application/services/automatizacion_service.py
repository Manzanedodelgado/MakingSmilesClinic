"""Motion (Automatizaciones) — capa de orquestación. Port de automation.engine.ts (.37).

La REGLA de cada disparador ES su fila en `plantillas_mensaje` (CONFIG = verdad):
sin fila activa, el disparador está APAGADO. El catálogo de disparadores y la
búsqueda de candidatos viven en automatizacion_triggers. Idempotencia por
`envios_automaticos` con ventana de días por disparador. Lo dispara el scheduler
cada minuto (solo centros con WhatsApp activo y el maestro `agente.alex.automatizacion`).

SEGURIDAD: `ejecutar(..., enviar=False)` es preview (no envía ni registra). El envío
real exige además el interruptor maestro encendido (como el kill-switch de la .37).
"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlmodel import Session, select

from application.services.comunicacion_service import ComunicacionService
from application.services.config_service import ConfigService
from application.services.automatizacion_triggers import (
    CATALOGO, CATALOGO_IDX, DEFAULTS, MAX_LOTE, OPCIONES_DEFAULT, TRIGGERS, Candidatos,
)
from domain.models.comunicacion import EnvioAutomatico, PlantillaMensaje
from domain.models.config import Integracion
from domain.models.core import Cita
from domain.services import telefono as tel
from infrastructure.external_apis.evolution_api import EvolutionError

# Clave CONFIG (sistema "ia"): lista de números autorizados en MODO PRUEBA.
# Si tiene algún número, el motor SOLO envía a esos y omite todo lo demás.
# Lista vacía / ausente = producción (envía a todos los candidatos).
CLAVE_MODO_PRUEBA = "motion.numeros_prueba"


def render(plantilla: str, v: dict) -> str:
    out = plantilla
    for k, val in v.items():
        out = out.replace("{{" + k + "}}", str(val or ""))
    return out


_DEDUP_SQL = text("""
    SELECT 1 FROM envios_automaticos
    WHERE centro_id = :c AND disparador = :d AND clave_objetivo = :k
      AND fecha_envio > :desde
    LIMIT 1
""")

_STATS_SQL = text("""
    SELECT disparador, COUNT(*) AS enviados, MAX(fecha_envio) AS ultimo
    FROM envios_automaticos WHERE centro_id = :c GROUP BY disparador
""")


class AutomatizacionService:
    def __init__(self, session: Session):
        self.session = session
        self.com = ComunicacionService(session)

    # ─────────────────────── MAESTRO (Config › IA's › Alex) ───────────────────────
    def maestro(self, centro_id: int) -> bool:
        alex = ConfigService(self.session).resolve(
            "agente.alex", centro_id=centro_id, sistema="ia", default={}) or {}
        return bool(alex.get("automatizacion"))

    def set_maestro(self, centro_id: int, activo: bool) -> bool:
        """Enciende/apaga `agente.alex.automatizacion` (misma clave que Config › IA's)."""
        svc = ConfigService(self.session)
        alex = svc.resolve("agente.alex", centro_id=centro_id, sistema="ia", default={}) or {}
        alex = {**alex, "automatizacion": bool(activo)}
        svc.set("agente.alex", alex, centro_id=centro_id, sistema="ia")
        return bool(activo)

    # ─────────────────────── MODO PRUEBA (lista blanca de números) ───────────────────────
    def numeros_prueba(self, centro_id: int) -> list[str]:
        v = ConfigService(self.session).resolve(
            CLAVE_MODO_PRUEBA, centro_id=centro_id, sistema="ia", default=[]) or []
        return [str(x) for x in v if str(x).strip()]

    def set_numeros_prueba(self, centro_id: int, numeros: list[str]) -> list[str]:
        limpios = [str(n).strip() for n in (numeros or []) if str(n).strip()]
        ConfigService(self.session).set(CLAVE_MODO_PRUEBA, limpios, centro_id=centro_id, sistema="ia")
        return limpios

    def _permitido(self, centro_id: int, telefono: str, allow: list[str]) -> bool:
        """En modo prueba solo se envía a la lista blanca. Sin lista → producción."""
        if not allow:
            return True
        return tel.en_lista(tel.normalizar(telefono), allow)

    def whatsapp_activo(self, centro_id: int) -> bool:
        ig = self.session.exec(select(Integracion).where(
            Integracion.centro_id == centro_id, Integracion.tipo == "whatsapp",
            Integracion.activo == True)).first()   # noqa: E712
        return ig is not None

    # ─────────────────────── REGLAS (fila en plantillas_mensaje) ───────────────────────
    def _fila(self, centro_id: int, disparador: str) -> Optional[PlantillaMensaje]:
        return self.session.exec(select(PlantillaMensaje).where(
            PlantillaMensaje.centro_id == centro_id,
            PlantillaMensaje.disparador == disparador)).first()

    def reglas(self, centro_id: int) -> dict:
        """Catálogo completo con su estado real: activo, plantilla y estadísticas de envío."""
        filas = {p.disparador: p for p in self.session.exec(select(PlantillaMensaje).where(
            PlantillaMensaje.centro_id == centro_id,
            PlantillaMensaje.disparador.isnot(None))).all()}   # type: ignore[union-attr]
        stats = {r[0]: {"enviados": r[1], "ultimo": r[2].isoformat() if r[2] else None}
                 for r in self.session.execute(_STATS_SQL, {"c": centro_id}).all()}
        data = []
        for c in CATALOGO:
            f = filas.get(c["disparador"])
            s = stats.get(c["disparador"], {})
            data.append({
                "disparador": c["disparador"], "nombre": f.nombre if f else c["nombre"],
                "grupo": c["grupo"], "descripcion": c["descripcion"],
                "solo_consentidos": bool(c.get("solo_consentidos")),
                "activo": bool(f and f.activo), "plantilla_id": f.id if f else None,
                "cuerpo": (f.cuerpo if f else None) or DEFAULTS.get(c["disparador"], ""),
                "tipo": f.tipo if f else "texto",
                "enviados": s.get("enviados", 0), "ultimo_envio": s.get("ultimo"),
            })
        return {"maestro": self.maestro(centro_id),
                "whatsapp_activo": self.whatsapp_activo(centro_id), "data": data}

    def set_regla(self, centro_id: int, disparador: str, activo: bool,
                  usuario_id: Optional[int] = None) -> dict:
        """ON/OFF de un disparador. Si no existe su fila, se crea con el cuerpo por defecto."""
        if disparador not in CATALOGO_IDX:
            raise ValueError(f"Disparador desconocido: {disparador}")
        f = self._fila(centro_id, disparador)
        if not f:
            c = CATALOGO_IDX[disparador]
            f = PlantillaMensaje(centro_id=centro_id, disparador=disparador,
                                 nombre=c["nombre"], cuerpo=DEFAULTS.get(disparador, ""),
                                 tipo="texto", activo=activo, updated_by=usuario_id)
        else:
            f.activo = activo
            f.updated_by = usuario_id
        self.session.add(f)
        self.session.commit()
        self.session.refresh(f)
        return {"disparador": disparador, "activo": f.activo, "plantilla_id": f.id}

    def guardar_plantilla_regla(self, centro_id: int, disparador: str, datos: dict,
                                usuario_id: Optional[int] = None) -> dict:
        """Edita nombre/cuerpo/tipo/opciones de la regla (upsert sobre plantillas_mensaje)."""
        if disparador not in CATALOGO_IDX:
            raise ValueError(f"Disparador desconocido: {disparador}")
        f = self._fila(centro_id, disparador)
        if not f:
            c = CATALOGO_IDX[disparador]
            f = PlantillaMensaje(centro_id=centro_id, disparador=disparador,
                                 nombre=c["nombre"], cuerpo="", activo=False)
        for campo in ("nombre", "cuerpo", "tipo", "opciones"):
            if datos.get(campo) is not None:
                setattr(f, campo, datos[campo])
        f.updated_by = usuario_id
        self.session.add(f)
        self.session.commit()
        self.session.refresh(f)
        return {"disparador": disparador, "plantilla_id": f.id, "activo": f.activo}

    # ─────────────────────── DEDUPE (ventana por disparador) ───────────────────────
    def _ya_enviado(self, centro_id: int, disparador: str, clave: str) -> bool:
        ventana = CATALOGO_IDX.get(disparador, {}).get("ventana_dias", 1)
        row = self.session.execute(_DEDUP_SQL, {
            "c": centro_id, "d": disparador, "k": clave,
            "desde": date.today() - timedelta(days=ventana)}).first()
        return row is not None

    def _registrar(self, centro_id: int, disparador: str, cand: dict) -> None:
        self.session.add(EnvioAutomatico(
            centro_id=centro_id, disparador=disparador, clave_objetivo=cand["clave"],
            canal="whatsapp", fecha_envio=date.today(), paciente_id=cand.get("paciente_id")))
        self.session.commit()

    # ─────────────────────── EJECUCIÓN ───────────────────────
    def ejecutar(self, centro_id: int, *, enviar: bool, solo: Optional[str] = None,
                 ahora: Optional[datetime] = None) -> dict:
        """Corre los disparadores ACTIVOS (o `solo` uno). enviar=False → preview.
        El envío real exige el maestro encendido (kill-switch, como la .37)."""
        if enviar and not self.maestro(centro_id):
            raise PermissionError("El envío de automatizaciones está APAGADO (interruptor maestro).")
        allow = self.numeros_prueba(centro_id)
        buscador = Candidatos(self.session, centro_id, ahora)
        resumen: dict[str, list] = {}
        omitidos = 0
        for c in CATALOGO:
            disparador = c["disparador"]
            if solo and disparador != solo:
                continue
            fila = self._fila(centro_id, disparador)
            activa = bool(fila and fila.activo)
            if not activa and not (solo and not enviar):
                continue   # apagada (el preview de UN disparador se permite aunque esté OFF)
            candidatos = TRIGGERS[disparador](buscador)[: MAX_LOTE.get(disparador, 200)]
            plantilla = (fila.cuerpo if fila else None) or DEFAULTS.get(disparador, "")
            # tipo/opciones: de la fila si existe (CONFIG = verdad), si no el default del
            # catálogo (para que el preview de una regla aún sin sembrar sea fiel).
            tipo = (fila.tipo if fila else None) or ("encuesta" if disparador in OPCIONES_DEFAULT else "texto")
            opciones = (fila.opciones if fila else None) or OPCIONES_DEFAULT.get(disparador)
            hechos = []
            for cand in candidatos:
                if self._ya_enviado(centro_id, disparador, cand["clave"]):
                    continue
                mensaje = render(plantilla, cand["vars"])
                item = {"clave": cand["clave"], "telefono": cand["telefono"], "mensaje": mensaje}
                permitido = self._permitido(centro_id, cand["telefono"], allow)
                if not permitido:
                    # MODO PRUEBA: fuera de la lista blanca no se envía NI se registra.
                    item["omitido"] = "modo_prueba"
                    omitidos += 1
                elif enviar:
                    item["enviado"] = self._despachar(centro_id, disparador, cand, mensaje, tipo, opciones)
                hechos.append(item)
            if hechos:
                resumen[disparador] = hechos
        return {"centro_id": centro_id, "enviado": enviar, "resultado": resumen,
                "modo_prueba": allow, "omitidos_por_modo_prueba": omitidos}

    def _despachar(self, centro_id: int, disparador: str, cand: dict, mensaje: str,
                   tipo: str = "texto", opciones: Optional[list[dict]] = None) -> bool:
        """Envía UN mensaje y registra la idempotencia. Un fallo no registra → reintentará."""
        # Segunda barrera del modo prueba: ninguna vía de envío puede saltarse la lista blanca.
        if not self._permitido(centro_id, cand["telefono"], self.numeros_prueba(centro_id)):
            return False
        try:
            if "consentimiento_cita_id" in cand:
                # Consentimiento: PDF COEM + enlace de firma (flujo ya existente; marca envio_doc).
                cita = self.session.get(Cita, cand["consentimiento_cita_id"])
                if cita:
                    self.com.enviar_consentimiento_cita(centro_id, cita)
            elif tipo == "encuesta" and opciones:
                # El paciente toca la opción (Confirmar/Cancelar) en vez de escribir una
                # palabra exacta — reutiliza el pipeline de encuestas ya probado
                # (PollContexto + _resolver_poll + _ejecutar_accion_poll).
                self.com.enviar_encuesta(centro_id, cand["telefono"], mensaje, opciones)
            else:
                self.com.enviar_texto(centro_id, cand["telefono"], mensaje, generado_por_ia=True)
            self._registrar(centro_id, disparador, cand)
            if "marcar_gestionada_cita_id" in cand:
                cita = self.session.get(Cita, cand["marcar_gestionada_cita_id"])
                if cita:
                    cita.anulacion_gestionada = True
                    self.session.add(cita)
                    self.session.commit()
            return True
        except EvolutionError:
            return False

    # ─────────────────────── SIEMBRA (idempotente) ───────────────────────
    def sembrar(self, centro_id: int, cuerpos: Optional[dict[str, str]] = None) -> int:
        """Crea las filas de regla que falten (activo=False, cuerpo por defecto o el dado).
        No toca las existentes. Devuelve cuántas creó."""
        creadas = 0
        for c in CATALOGO:
            if self._fila(centro_id, c["disparador"]):
                continue
            cuerpo = (cuerpos or {}).get(c["disparador"]) or DEFAULTS.get(c["disparador"], "")
            opciones = OPCIONES_DEFAULT.get(c["disparador"])
            self.session.add(PlantillaMensaje(
                centro_id=centro_id, disparador=c["disparador"], nombre=c["nombre"],
                cuerpo=cuerpo, tipo=("encuesta" if opciones else "texto"), opciones=opciones,
                activo=False))
            creadas += 1
        self.session.commit()
        return creadas
