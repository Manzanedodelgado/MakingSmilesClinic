"""INICIO — el pulso de la clínica.

Qué es: la lista de cosas que HOY necesitan que una persona haga algo, cada una con el
enlace al sitio exacto donde se resuelve. No es un cuadro de mandos: aquí no hay tarjetas
con cifras grandes que nadie sabe qué hacer con ellas. Si algo aparece en esta pantalla es
porque se puede pinchar y atender.

Reglas que sigue:
  · Un solo viaje. Todo se resuelve en una llamada y con consultas agrupadas (nunca una
    por fila), porque esto se pinta en cada carga de la app.
  · Cada bloque respeta el permiso de su área. Quien no ve Gestoría no ve sus facturas
    aquí; el panel no es una puerta trasera a datos de otra área.
  · Nada inventado. Un bloque sin datos dice "nada pendiente"; no se rellena con estimaciones.
"""
from __future__ import annotations

import logging

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, func, select

from domain.models.comunicacion import Conversacion, Mensaje
from domain.models.core import Paciente
from domain.models.economico import FormaPago, Pago, Presupuesto
from domain.models.gestoria import Deuda, Gasto, ModeloFiscal, MovimientoBancario

logger = logging.getLogger(__name__)

# Urgencia: 0 = al día · 1 = conviene mirarlo · 2 = se está pasando el arroz.
NORMAL, ATENCION, URGENTE = 0, 1, 2


# Ruta de configuración de cada agente en el frontend. OJO: la sección se llama `agentes`
# (src/app/(app)/configuracion/agentes/[sub]), no `ias` — enlazar a /configuracion/ias/*
# daba 404 en el panel de Pulso. Solo estos ids tienen pantalla propia; los demás agentes
# (victor, aura, gestor_multimodal...) se ven en el catálogo, que los lista desde agentes.py.
_SUBS_AGENTE = {"alex", "gestor", "centinela", "entrenamiento", "modelos", "catalogo"}


def _ruta_agente(agente_id: str) -> str:
    sub = agente_id if agente_id in _SUBS_AGENTE else "catalogo"
    return f"/configuracion/agentes/{sub}"


def _f(v) -> float:
    return round(float(v or 0), 2)


def _hace(cuando: Optional[datetime]) -> str:
    """'hace 3 h', 'hace 2 d'. En lenguaje llano, que es como se lee de un vistazo."""
    if not cuando:
        return "—"
    seg = (datetime.now() - cuando).total_seconds()
    if seg < 3600:
        return f"hace {max(1, int(seg // 60))} min"
    if seg < 86400:
        return f"hace {int(seg // 3600)} h"
    dias = int(seg // 86400)
    return "ayer" if dias == 1 else f"hace {dias} días"


class PulsoService:
    def __init__(self, session: Session, centro_id: int, permisos: set[str]):
        self.s = session
        self.centro_id = centro_id
        self.p = permisos
        self.hoy = date.today()

    def _puede(self, *codigos: str) -> bool:
        return any(c in self.p for c in codigos)

    # ─────────────────────────── el pulso completo ───────────────────────────
    def pulso(self) -> dict:
        bloques = [b for b in (
            self._whatsapp(),
            self._llamadas(),
            self._firmas(),
            self._gestoria(),
            self._impuestos(),
            self._presupuestos(),
        ) if b is not None]
        return {
            "fecha": self.hoy.isoformat(),
            "bloques": bloques,
            "hoy": self._hoy(),
            "sistemas": self._sistemas(),
        }

    # ─────────────────────────── SISTEMAS CONECTADOS ───────────────────────────
    def _sistemas(self) -> list[dict]:
        """Estado de los sistemas de los que depende la clínica.

        Se leen de las MISMAS fuentes que el módulo IA (ComunicacionService, la salud del
        Gestor IA y CONFIG); no hay una segunda verdad. Si una lectura falla, ese sistema
        se marca 'sin respuesta' — jamás se pinta en verde por no haber podido comprobarlo.

        `estado`: ok | reposo | caido | desconocido. 'reposo' es apagado A PROPÓSITO
        (Alex con los canales cerrados), que no es una avería y no debe alarmar."""
        out: list[dict] = []

        def add(bid, nombre, estado, detalle, enlace, padre=None):
            out.append({"id": bid, "nombre": nombre, "estado": estado,
                        "detalle": detalle, "enlace": enlace, "padre": padre})

        # Una sola lectura de CONFIG para todo el bloque (antes se abría por agente).
        from application.services.config_service import ConfigService
        try:
            cfg_ia = ConfigService(self.s).for_scope(centro_id=self.centro_id, sistema="ia")
        except Exception:  # raiz: config de IA no disponible -> se asume sin configuración; el sistema se marca "sin respuesta"
            cfg_ia = {}

        # ── WhatsApp (Evolution) — el canal por el que entra y sale todo
        if self._puede("comunicacion.ver"):
            try:
                from application.services.comunicacion_service import ComunicacionService
                w = ComunicacionService(self.s).estado(self.centro_id)
                add("whatsapp", "WhatsApp",
                    "ok" if w.get("conectado") else ("caido" if w.get("evolution") else "desconocido"),
                    "Conectado" if w.get("conectado") else (w.get("estado") or "Sin conexión"),
                    "/configuracion/conectores/whatsapp")
            except Exception:  # raiz: Evolution/WhatsApp sin respuesta -> sistema marcado "desconocido"
                add("whatsapp", "WhatsApp", "desconocido", "Sin respuesta", "/configuracion/conectores/whatsapp")

        # ── LOS AGENTES, en su jerarquía real: Alex · Victor (con Aura debajo) · Gestor.
        # Aura NO es hermana de Victor: es su especialización dentro del gabinete, así que
        # cuelga de él (`padre`) y la pantalla la pinta anidada.
        salud_gestor = None
        if self._puede("gestoria.ver", "gestoria.facturacion.ver"):
            try:
                from application.services.gmail_ingest_service import GmailIngestService
                salud_gestor = GmailIngestService(self.s).health(self.centro_id) or {}
            except Exception:  # raiz: salud del Gestor IA no disponible -> se omite y el agente cae a su interruptor
                salud_gestor = None

        if self._puede("config.ver", "pacientes.ver"):
            try:
                from application.services.agentes_config import estado as estado_agentes
                for e in estado_agentes(self.s, self.centro_id):
                    detalle = (f"{len(e['capacidadesActivas'])}/{e['capacidadesTotales']} capacidades"
                               if e["activa"] else "Desactivado")
                    estado = "ok" if e["operativa"] else "reposo"

                    if e["id"] == "alex":
                        # Alex vale lo que valgan sus canales: sin WhatsApp ni voz no atiende
                        # a nadie por muy encendido que esté su interruptor.
                        canales = (cfg_ia.get("agente.alex") or {}).get("canales") or {}
                        vivos = [n for n, k in (("WhatsApp", "whatsapp"), ("Voz", "voicebot"))
                                 if canales.get(k)]
                        detalle = " · ".join(vivos) if vivos else "Sin canal activo"
                        estado = "ok" if (e["operativa"] and vivos) else "reposo"
                    elif e["id"] == "gestor" and salud_gestor is not None:
                        # El Gestor es el único que ya trabaja: su estado real pesa más que
                        # su interruptor, y lo sabe su propia salud (IA/buzón/archivo).
                        estado = "ok" if salud_gestor.get("iaOk") else "caido"
                        detalle = salud_gestor.get("iaMotivo") or detalle
                    elif e["bloqueadoPor"]:
                        detalle = f"Encendida, pero {e['bloqueadoPor']} está apagado"

                    add(e["id"], e["nombre"], estado, detalle,
                        _ruta_agente(e["id"]), padre=e["dependeDe"])
            except Exception:  # raiz: agentes IA sin respuesta -> se marca el bloque "desconocido"
                add("agentes", "Agentes IA", "desconocido", "Sin respuesta",
                    "/configuracion/agentes/catalogo")

        # ── CENTINELA: aparte. No es un agente conversacional, es la salud del sistema.
        if self._puede("config.ver"):
            try:
                cen = (ConfigService(self.s).for_scope(centro_id=self.centro_id, sistema="centinela")
                       .get("centinela.config") or {})
                activa = cen.get("activa") is True
                objetivos = (cen.get("vigilancia") or {}).get("objetivos") or {}
                n = sum(1 for v in objetivos.values() if v)
                add("centinela", "Centinela", "ok" if activa else "reposo",
                    f"{n} objetivos vigilados" if activa else "Vigilancia desactivada",
                    "/configuracion/agentes/centinela")
            except Exception:  # raiz: config de Centinela no disponible -> marcado "desconocido"
                add("centinela", "Centinela", "desconocido", "Sin respuesta",
                    "/configuracion/agentes/centinela")

        # ── Conectores del Gestor: fallan por separado, así que se miran por separado.
        if salud_gestor is not None:
            add("buzon", "Buzón", "ok" if salud_gestor.get("imapOk") else "caido",
                "Conectado" if salud_gestor.get("imapOk") else "Sin conectar",
                "/configuracion/agentes/gestor", padre="gestor")
            add("drive", "Drive", "ok" if salud_gestor.get("driveOk") else "caido",
                "Conectado" if salud_gestor.get("driveOk") else "Sin conectar",
                "/configuracion/agentes/gestor", padre="gestor")

        # Cada hijo, JUSTO detrás de su padre. Sin esto los conectores del Gestor salían
        # después de Centinela y la sangría mentía.
        por_padre: dict = {}
        for x in out:
            por_padre.setdefault(x.get("padre"), []).append(x)
        ordenado = []
        for x in por_padre.get(None, []):
            ordenado.append(x)
            ordenado.extend(por_padre.get(x["id"], []))
        huerfanos = [x for x in out if x not in ordenado]
        return ordenado + huerfanos

    # ─────────────────────────── 1 · WHATSAPP ───────────────────────────
    def _whatsapp(self) -> Optional[dict]:
        if not self._puede("comunicacion.ver", "pacientes.ver"):
            return None
        convs = self.s.exec(select(Conversacion).where(
            Conversacion.centro_id == self.centro_id,
            Conversacion.archivada == False,  # noqa: E712
            Conversacion.estado != "resuelta",  # "Resuelto" en esta tarjeta la saca de pendientes
        )).all()
        # Pendiente de verdad = el ÚLTIMO mensaje es del paciente. Que haya "no leídos" no
        # basta: se puede haber contestado sin marcar leído, y al revés.
        ids = [c.id for c in convs]
        ultimos: dict[int, Mensaje] = {}
        if ids:
            for m in self.s.exec(select(Mensaje).where(Mensaje.conversacion_id.in_(ids))
                                 .order_by(Mensaje.enviado_at)):
                ultimos[m.conversacion_id] = m       # se queda el más reciente
        pendientes = [c for c in convs
                      if (u := ultimos.get(c.id)) is not None and u.direccion == "entrante"]
        pendientes.sort(key=lambda c: c.ultimo_mensaje_at or datetime.min)   # el que más espera, primero
        nombres = self._nombres([c.paciente_id for c in pendientes])

        def urgencia(c) -> int:
            if not c.ultimo_mensaje_at:
                return NORMAL
            h = (datetime.now() - c.ultimo_mensaje_at).total_seconds() / 3600
            return URGENTE if h >= 24 else ATENCION if h >= 4 else NORMAL

        return self._bloque(
            "whatsapp", "WhatsApp sin responder", "Escribió el paciente y nadie ha contestado",
            [{"id": c.id,
              "titulo": nombres.get(c.paciente_id) or c.telefono or "Sin identificar",
              "detalle": (c.ultimo_mensaje or "")[:90],
              "cuando": _hace(c.ultimo_mensaje_at),
              "urgencia": urgencia(c),
              # Convención de deep-link que ya usa la agenda: no se inventa otra.
              "enlace": f"/comunicacion?tel={c.telefono or ''}",
              "accion": "Responder"} for c in pendientes],
            vacio="Ninguna conversación esperando respuesta.")

    # ─────────────────────────── 2 · LLAMADAS ───────────────────────────
    def _llamadas(self) -> Optional[dict]:
        if not self._puede("comunicacion.ver", "pacientes.ver"):
            return None
        from sqlmodel import text
        # Tablas jóvenes (aún sin uso): se leen por SQL directo y con red por si no existen,
        # para que el panel no se caiga si una migración va por detrás.
        try:
            rows = self.s.exec(text("""
                SELECT l.id, l.paciente_id, l.telefono, l.entrada, l.created_at
                  FROM llamadas_voz l
                 WHERE l.centro_id = :c AND COALESCE(l.estado,'') <> 'devuelta'
                 ORDER BY l.created_at LIMIT 50
            """), params={"c": self.centro_id}).all()
        except Exception:  # raiz: tabla llamadas_voz aún ausente (migración por detrás) -> sin filas; el panel no se cae
            rows = []
        nombres = self._nombres([r[1] for r in rows])
        return self._bloque(
            "llamadas", "Llamadas sin devolver", "Entraron y no se ha devuelto la llamada",
            [{"id": r[0],
              "titulo": nombres.get(r[1]) or r[2] or "Número desconocido",
              "detalle": (r[3] or "")[:90],
              "cuando": _hace(r[4]),
              "urgencia": URGENTE if r[4] and (datetime.now() - r[4]).days >= 1 else ATENCION,
              "enlace": f"/comunicacion?tel={r[2] or ''}",
              "accion": "Devolver"} for r in rows],
            vacio="Ninguna llamada pendiente de devolver.")

    # ─────────────────────────── 3 · FIRMAS ───────────────────────────
    def _firmas(self) -> Optional[dict]:
        if not self._puede("pacientes.ver"):
            return None
        from sqlmodel import text
        try:
            rows = self.s.exec(text("""
                SELECT d.id, d.paciente_id, d.tipo_doc, d.descripcion, d.fecha
                  FROM documentos_firmados d
                 WHERE NOT d.firmado
                 ORDER BY d.fecha NULLS LAST LIMIT 50
            """)).all()
        except Exception:  # raiz: tabla documentos_firmados aún ausente (migración por detrás) -> sin filas
            rows = []
        nombres = self._nombres([r[1] for r in rows])
        return self._bloque(
            "firmas", "Documentos sin firmar", "Consentimientos y documentos a la espera de firma",
            [{"id": r[0],
              "titulo": nombres.get(r[1]) or "Paciente",
              "detalle": r[3] or r[2] or "Documento",
              "cuando": r[4].strftime("%d/%m/%Y") if r[4] else "—",
              "urgencia": ATENCION,
              "enlace": f"/pacientes/{r[1]}/documentos",
              "accion": "Abrir y firmar"} for r in rows],
            vacio="Ningún documento pendiente de firma.")

    # ─────────────────────────── 4 · GESTORÍA ───────────────────────────
    def _gestoria(self) -> Optional[dict]:
        if not self._puede("gestoria.ver"):
            return None
        revisar = self.s.exec(select(Gasto).where(
            Gasto.centro_id == self.centro_id, Gasto.estado == "revisar"
        ).order_by(Gasto.fecha.desc()).limit(50)).all()
        piden = self.s.exec(select(MovimientoBancario).where(
            MovimientoBancario.centro_id == self.centro_id,
            MovimientoBancario.estado_concil == "requiere_datos"
        ).order_by(MovimientoBancario.fecha_operacion).limit(50)).all()
        # Cada fila enlaza a SU apunte concreto (?mov=<id>): Debe/Haber lo aísla en el buscador.
        # El importe va delante porque es lo que distingue una cuota de otra de un vistazo.
        items = [{"id": f"m{m.id}",
                  "titulo": f"{_f(abs(m.importe))} € · {m.fecha_operacion.strftime('%d/%m/%Y')}",
                  "detalle": (m.concepto_util or "Movimiento sin concepto")[:90],
                  "cuando": m.fecha_operacion.strftime("%d/%m/%Y"),
                  "urgencia": URGENTE,
                  "enlace": f"/gestoria/facturacion?tab=debehaber&mov={m.id}",
                  "accion": "Completar"} for m in piden]
        items += [{"id": f"g{g.id}",
                   "titulo": g.proveedor_extraido or "Factura sin proveedor",
                   "detalle": (g.incidencia or "Faltan datos")[:80] + f" · {_f(g.total)} €",
                   "cuando": g.fecha.strftime("%d/%m/%Y") if g.fecha else "—",
                   "urgencia": ATENCION,
                   "enlace": f"/gestoria/facturacion?tab=facturas&gasto={g.id}",
                   "accion": "Revisar"} for g in revisar]
        total = (self._cuantos(Gasto, Gasto.centro_id == self.centro_id, Gasto.estado == "revisar")
                 + self._cuantos(MovimientoBancario,
                                 MovimientoBancario.centro_id == self.centro_id,
                                 MovimientoBancario.estado_concil == "requiere_datos"))
        return self._bloque("gestoria", "Facturas y banco", "Documentos que no se pueden dar por buenos todavía",
                            items, vacio="Contabilidad al día.", total=total)

    # ─────────────────────────── 5 · IMPUESTOS ───────────────────────────
    def _impuestos(self) -> Optional[dict]:
        if not self._puede("gestoria.ver", "gestoria.facturacion.ver"):
            return None
        rows = self.s.exec(select(ModeloFiscal).where(
            ModeloFiscal.centro_id == self.centro_id,
            ModeloFiscal.estado != "presentado",
        ).order_by(ModeloFiscal.fecha_limite)).all()

        def urg(m) -> int:
            if not m.fecha_limite:
                return NORMAL
            dias = (m.fecha_limite - self.hoy).days
            return URGENTE if dias <= 7 else ATENCION if dias <= 30 else NORMAL

        def cuando(m) -> str:
            if not m.fecha_limite:
                return "sin fecha límite"
            dias = (m.fecha_limite - self.hoy).days
            if dias < 0:
                return f"VENCIDO hace {-dias} días"
            return "vence hoy" if dias == 0 else f"quedan {dias} días"

        return self._bloque(
            "impuestos", "Impuestos y plazos", "Modelos fiscales sin presentar",
            [{"id": m.id,
              "titulo": f"Modelo {m.modelo} · {m.periodo or ''} {m.ejercicio or ''}".strip(),
              "detalle": f"{m.estado} · límite {m.fecha_limite.strftime('%d/%m/%Y')}" if m.fecha_limite else m.estado,
              "cuando": cuando(m),
              "urgencia": urg(m),
              "enlace": (f"/gestoria/facturacion?tab=impuestos"
                         f"&modelo={m.modelo}&periodo={m.periodo or ''}&ejercicio={m.ejercicio or ''}"),
              "accion": "Ver modelo"} for m in rows],
            vacio="Ningún modelo pendiente de presentar.")

    # ─────────────────────────── 6 · PRESUPUESTOS ───────────────────────────
    def _presupuestos(self) -> Optional[dict]:
        if not self._puede("pacientes.ver"):
            return None
        # Entregado (estado 1) y sin respuesta pasadas dos semanas: es dinero que se enfría.
        corte = self.hoy - timedelta(days=15)
        rows = self.s.exec(select(Presupuesto).where(
            Presupuesto.centro_id == self.centro_id,
            Presupuesto.estado_id == 1, Presupuesto.fecha <= corte,
        ).order_by(Presupuesto.total.desc()).limit(50)).all()
        nombres = self._nombres([p.paciente_id for p in rows])
        return self._bloque(
            "presupuestos", "Presupuestos sin respuesta", "Entregados hace más de 15 días y sin aceptar",
            [{"id": p.id,
              "titulo": nombres.get(p.paciente_id) or "Paciente",
              "detalle": f"{p.titulo or 'Presupuesto'} · {_f(p.total)} €",
              "cuando": p.fecha.strftime("%d/%m/%Y") if p.fecha else "—",
              "urgencia": NORMAL,
              "enlace": f"/pacientes/{p.paciente_id}/presupuestos?pre={p.id}",
              "accion": "Seguimiento"} for p in rows],
            vacio="Todos los presupuestos tienen respuesta.",
            total=self._cuantos(Presupuesto, Presupuesto.centro_id == self.centro_id,
                                Presupuesto.estado_id == 1, Presupuesto.fecha <= corte))

    # ─────────────────────────── EL DÍA: agenda, caja, deuda ───────────────────────────
    # ─────────────────────────── CITAS DEL DÍA (Cover Flow de Inicio) ───────────────────────────
    def citas(self, fecha: date, *, agenda_id: Optional[int] = None,
              colaborador_id: Optional[int] = None, gabinete_id: Optional[int] = None,
              estado_id: Optional[int] = None, tipo_cita_id: Optional[int] = None) -> dict:
        """Citas de un día con filtros + las opciones de cada filtro.

        Todos los filtros acotan DENTRO del centro autenticado (el WHERE de centro va siempre),
        así que un id de otro centro solo devuelve vacío. Las opciones de gabinete/estado/tipo
        son las de la agenda elegida (la config de agenda es por agenda)."""
        from sqlmodel import text
        if not self._puede("citas.ver", "pacientes.ver"):
            return {"fecha": fecha.isoformat(), "permitido": False, "citas": [], "opciones": {}}

        where = ["c.centro_id = :c", "c.fecha = :f",
                 # Anulada por CÓDIGO: los ids de estado son distintos en cada centro/agenda.
                 "COALESCE(e.codigo, '') <> 'anulada'"]
        params: dict = {"c": self.centro_id, "f": fecha}
        for col, val in (("agenda_id", agenda_id), ("colaborador_id", colaborador_id),
                         ("gabinete_id", gabinete_id), ("estado_id", estado_id),
                         ("tipo_cita_id", tipo_cita_id)):
            if val is not None:
                where.append(f"c.{col} = :{col}")
                params[col] = val
        try:
            filas = self.s.exec(text(f"""
                SELECT c.id, c.hora, c.paciente_id,
                       -- La cita solo trae nombre inline si no hay ficha; si la hay, manda la ficha.
                       COALESCE(NULLIF(c.nombre, ''), p.nombre) AS nombre,
                       COALESCE(NULLIF(c.apellidos, ''), p.apellidos) AS apellidos,
                       e.nombre AS estado, c.duracion_min,
                       c.colaborador_id,
                       -- Igual que el nombre: el móvil de la ficha manda; el de la cita es el respaldo
                       -- (muchas citas no lo copian y el paciente sí lo tiene).
                       COALESCE(NULLIF(p.telefono_movil, ''), NULLIF(c.telefono_movil, '')) AS telefono_movil,
                       g.nombre AS gabinete, t.nombre AS tipo,
                       COALESCE(p.num_historia, c.num_historia) AS num_historia,
                       TRIM(CONCAT(u.nombre, ' ', COALESCE(u.apellidos, ''))) AS doctor,
                       c.gabinete_id, c.tipo_cita_id, c.estado_id, c.agenda_id,
                       e.codigo AS estado_codigo
                  FROM citas c
                  LEFT JOIN pacientes p ON p.id = c.paciente_id
                  LEFT JOIN estados_cita e ON e.id = c.estado_id
                  LEFT JOIN gabinetes g ON g.id = c.gabinete_id
                  LEFT JOIN tipos_cita t ON t.id = c.tipo_cita_id
                  LEFT JOIN colaboradores co ON co.id = c.colaborador_id
                  LEFT JOIN usuario_periodos up ON up.id = co.periodo_id
                  LEFT JOIN usuarios u ON u.id = up.usuario_id
                 WHERE {" AND ".join(where)}
                 ORDER BY c.hora, c.id
            """), params=params).all()
        except Exception:  # raiz: consulta de citas del día falla -> sin filas; el panel no se cae
            logger.exception("inicio · citas del día")
            filas = []

        pac_ids = [f[2] for f in filas if f[2]]
        # Previsión de cobro: lo que ya deben los pacientes que vienen ese día. Es un hecho
        # (deuda viva), no una estimación de lo que "podrían" aceptar.
        deuda_pac: dict[int, float] = {}
        if pac_ids:
            for pid, tot in self.s.exec(
                    select(Deuda.paciente_id, func.sum(Deuda.importe_pendiente))
                    .where(Deuda.paciente_id.in_(pac_ids), Deuda.importe_pendiente > 0,
                           Deuda.incobrable == False)  # noqa: E712
                    .group_by(Deuda.paciente_id)).all():
                deuda_pac[pid] = _f(tot)
        citas = [{"id": f[0], "hora": (f[1] or "")[:5],
                  "paciente": f"{f[4] or ''}, {f[3] or ''}".strip(", ") or "Sin nombre",
                  "pacienteId": f[2], "estado": f[5] or "Planificada",
                  "duracion": f[6],
                  "porCobrar": deuda_pac.get(f[2], 0.0),
                  "enlace": f"/pacientes/{f[2]}/ficha" if f[2] else "/agenda",
                  "colaboradorId": f[7], "telefono": f[8], "gabinete": f[9], "tipo": f[10],
                  "numHistoria": f[11], "doctor": f[12] or None,
                  "gabineteId": f[13], "tipoCitaId": f[14], "estadoId": f[15], "agendaId": f[16],
                  # Código semántico (planificada, confirmada, recepcion…): el flujo de la visita
                  # en Inicio se decide por código, nunca por id ni por el nombre visible.
                  "estadoCodigo": f[17]}
                 for f in filas]
        return {"fecha": fecha.isoformat(), "permitido": True, "citas": citas,
                "opciones": self._opciones_citas(agenda_id)}

    def _opciones_citas(self, agenda_id: Optional[int]) -> dict:
        from sqlmodel import text
        c = self.centro_id

        def q(sql: str, **extra) -> list[dict]:
            # Columnas opcionales a partir de la 3.ª (p. ej. el código del estado).
            return [{"id": r[0], "nombre": r[1],
                     **({"codigo": r[2]} if len(r) > 2 else {}),
                     **({"agendaId": r[3]} if len(r) > 3 else {})}
                    for r in self.s.exec(text(sql), params={"c": c, **extra}).all()]

        por_agenda = " AND agenda_id = :a" if agenda_id is not None else ""
        a = {"a": agenda_id} if agenda_id is not None else {}
        return {
            "agendas": q("SELECT id, nombre FROM agendas WHERE centro_id = :c AND activo"
                         " ORDER BY orden NULLS LAST, id"),
            "gabinetes": q("SELECT id, nombre FROM gabinetes WHERE centro_id = :c AND activo"
                           f"{por_agenda} ORDER BY nombre", **a),
            "estados": q("SELECT id, nombre, codigo, agenda_id FROM estados_cita WHERE centro_id = :c"
                         f" AND codigo <> 'anulada'{por_agenda} ORDER BY orden NULLS LAST, id", **a),
            "tipos": q("SELECT id, nombre FROM tipos_cita WHERE centro_id = :c AND activo"
                       f"{por_agenda} ORDER BY nombre", **a),
            # REGLA DURA: en un selector solo personal ACTIVO = periodo abierto (fecha_baja vacía)
            # y de ESTE centro. `activo` solo no basta: hay colaboradores activo=true con baja.
            "doctores": q("""SELECT co.id, TRIM(CONCAT(u.nombre, ' ', COALESCE(u.apellidos, '')))
                               FROM colaboradores co
                               JOIN usuario_periodos up ON up.id = co.periodo_id
                               JOIN usuarios u ON u.id = up.usuario_id
                              WHERE up.centro_id = :c AND co.activo AND up.fecha_baja IS NULL
                              ORDER BY 2"""),
        }

    def _hoy(self) -> dict:
        citas = self.citas(self.hoy)["citas"]

        caja: dict = {}
        if self._puede("gestoria.ver", "pacientes.ver"):
            filas = self.s.exec(
                select(FormaPago.nombre, func.count(Pago.id), func.sum(Pago.importe))
                .select_from(Pago).join(FormaPago, FormaPago.id == Pago.forma_pago_id, isouter=True)
                .where(Pago.centro_id == self.centro_id, Pago.fecha == self.hoy,
                       Pago.anulado == False)  # noqa: E712
                .group_by(FormaPago.nombre)).all()
            caja = {"total": _f(sum((f[2] or Decimal("0")) for f in filas)),
                    "porForma": [{"forma": f[0] or "Sin indicar", "n": f[1], "importe": _f(f[2])}
                                 for f in filas]}

        deuda: dict = {}
        if self._puede("gestoria.ver", "pacientes.ver"):
            n, total = self.s.exec(
                select(func.count(Deuda.id), func.sum(Deuda.importe_pendiente))
                .where(Deuda.centro_id == self.centro_id, Deuda.importe_pendiente > 0,
                       Deuda.incobrable == False)).one()  # noqa: E712
            deuda = {"n": n or 0, "total": _f(total)}

        return {"citas": citas, "caja": caja, "deuda": deuda,
                "previstoHoy": _f(sum(c["porCobrar"] for c in citas))}

    # ─────────────────────────── utilidades ───────────────────────────
    def _nombres(self, ids: list[Optional[int]]) -> dict[int, str]:
        """Nombres de paciente en UNA consulta (nunca una por fila)."""
        limpio = [i for i in ids if i]
        if not limpio:
            return {}
        return {p.id: f"{p.apellidos or ''}, {p.nombre or ''}".strip(", ")
                for p in self.s.exec(select(Paciente).where(Paciente.id.in_(limpio)))}

    @staticmethod
    def _bloque(bid: str, titulo: str, subtitulo: str, items: list, *,
                vacio: str, total: Optional[int] = None) -> dict:
        """Empaqueta un bloque.

        `total` DEBE ser el recuento real cuando la consulta lleva LIMIT; si se dejara
        `len(items)` el panel diría "50 presupuestos" habiendo 2.052, que es exactamente el
        engaño que esta pantalla existe para evitar."""
        return {"id": bid, "titulo": titulo, "subtitulo": subtitulo,
                "total": len(items) if total is None else total, "items": items[:10],
                "urgencia": max((i["urgencia"] for i in items), default=NORMAL),
                "vacio": vacio}

    def _cuantos(self, modelo, *condiciones) -> int:
        """Recuento real de un bloque, sin traerse las filas."""
        return self.s.exec(select(func.count(modelo.id)).where(*condiciones)).one() or 0
