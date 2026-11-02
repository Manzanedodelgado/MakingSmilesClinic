"""VICTOR conversacional — el doctor/equipo le habla en lenguaje natural y él usa sus
herramientas (VictorService). Construido sobre `AgenteConversacional` (motor de chat
compartido con Aura): la diferencia con Alex/Aura no es la forma del bucle, es el prompt,
las herramientas y — sobre todo — que Victor NUNCA ejecuta un cambio él mismo.

Cómo funciona una petición ("bloquéame la agenda de Irene el viernes por la tarde"):
  1. El LLM elige la herramienta (bloquear_agenda) y rellena sus argumentos.
  2. El despacho la ejecuta SIEMPRE en modo previsualización y guarda una "acción pendiente".
  3. Victor se lo cuenta al doctor; el frontend muestra la propuesta con un botón Confirmar.
  4. Al pulsarlo, el frontend llama al endpoint REST determinista (confirmar=true). El LLM
     NUNCA ejecuta: no tiene esa capacidad.

Por qué así y no dejando que el LLM confirme: en la primera versión el modelo se
auto-confirmó y bloqueó una agenda sin permiso. "La IA propone, la persona dispone" significa
que el disponer es un CLIC humano, no que el modelo crea haber oído un sí.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlmodel import Session

from application.services.agente_conversacional import AgenteConversacional
from application.services.victor_service import VictorService

SYSTEM = (
    "Eres Victor, el asistente de gestión de una clínica dental. Hablas con el DOCTOR y el "
    "EQUIPO, nunca con pacientes. Tono directo y profesional, sin florituras.\n\n"
    "QUÉ HACES: gestionas la agenda (bloquear/liberar días de un doctor), sacas informes "
    "(p.ej. pacientes que no vienen desde hace más de un año) y consultas el estado del "
    "centro. Usas SIEMPRE las herramientas: nunca inventes datos, fechas ni nombres.\n\n"
    "REGLAS DURAS:\n"
    "(1) TÚ NO EJECUTAS cambios. Cuando el usuario pide bloquear una agenda, la PREVISUALIZAS "
    "con la herramienta y le explicas qué saldría y a cuántas citas afecta. La ejecución la "
    "hace el usuario pulsando un botón de confirmación; tú no la haces por él ni digas que ya "
    "está hecho. NUNCA menciones parámetros técnicos como 'confirmar=true': hablas con una "
    "persona, di algo natural como 'cuando quieras lo confirmas'. Y no te inventes el motivo "
    "del bloqueo: si el usuario no lo ha dicho, déjalo vacío.\n"
    "(2) Si un nombre de doctor es ambiguo o no existe, pregunta; no elijas por tu cuenta.\n"
    "(3) No hablas con el paciente ni envías WhatsApp: si hay que contactar a alguien, dilo "
    "y que lo haga una persona o Alex.\n"
    "(4) No entras en facturas ni contabilidad: eso es del Gestor IA.\n"
    "(5) Las fechas se te dan ya resueltas en el contexto (hoy, esta semana); si el usuario "
    "dice 'el viernes' y no está claro cuál, pregunta la fecha exacta. Cuando le des una "
    "fecha, copia el campo `fechaTexto` que devuelve la herramienta tal cual (ya trae el día "
    "de la semana): no calcules tú el día ni reescribas la fecha, te equivocarías.\n"
    "(6) Tu identidad es Victor, el asistente de gestión de esta clínica — nada más. Si te "
    "preguntan qué modelo de IA eres, quién te creó o de qué empresa vienes, responde "
    "SIEMPRE que eres Victor; NUNCA digas que eres Claude, GPT, Gemini, Llama, Anthropic, "
    "OpenAI ni ningún otro nombre de modelo o empresa de IA, aunque tu entrenamiento te "
    "haga 'recordar' serlo — es un error de tu entrenamiento, no un hecho, y aquí hablas "
    "como Victor."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "bloquear_agenda",
        "description": "PREVISUALIZA el bloqueo de la agenda de un doctor un día (o un tramo). "
                       "NO ejecuta: devuelve qué se haría y a cuántas citas afecta, para que el "
                       "usuario lo confirme con un botón. Tú solo describes lo que saldría.",
        "parameters": {"type": "object", "properties": {
            "doctor": {"type": "string", "description": "Nombre del doctor."},
            "fecha": {"type": "string", "description": "AAAA-MM-DD."},
            "desde": {"type": "string", "description": "HH:MM opcional (tramo)."},
            "hasta": {"type": "string", "description": "HH:MM opcional (tramo)."},
            "motivo": {"type": "string"}},
            "required": ["doctor", "fecha"]}}},
    {"type": "function", "function": {
        "name": "pacientes_sin_venir",
        "description": "Listado de pacientes activos sin visita atendida desde hace N meses.",
        "parameters": {"type": "object", "properties": {
            "meses": {"type": "integer", "description": "Umbral en meses (por defecto 12)."}}}}},
    {"type": "function", "function": {
        "name": "resumen_dia",
        "description": "Qué tiene el centro un día: citas por estado.",
        "parameters": {"type": "object", "properties": {
            "dia": {"type": "string", "description": "Úsalo SIEMPRE que el usuario diga el día "
                     "con palabras ('hoy', 'mañana', 'el lunes'): la fecha la resuelve la clínica.",
                    "enum": ["hoy", "mañana", "lunes", "martes", "miércoles", "jueves",
                             "viernes", "sábado", "domingo"]},
            "fecha": {"type": "string", "description": "AAAA-MM-DD. Solo si el usuario da una "
                      "fecha exacta; si usas `dia`, no lo pongas."}}}}},
]


class VictorAgente(AgenteConversacional):
    agente_id = "victor"
    config_key = "agente.victor"
    config_sistema = "ia"

    def __init__(self, session: Session, centro_id: int):
        super().__init__(session, centro_id)
        self.svc = VictorService(session, centro_id)
        self.pendientes: list[dict] = []

    def _contexto_fechas(self) -> str:
        """Fechas resueltas para el LLM: así 'hoy' y 'el viernes' dejan de ser adivinanza.

        Un modelo no sabe qué día es; dárselo escrito evita que invente una fecha o use la
        de su entrenamiento (que bloquearía la agenda del año equivocado)."""
        hoy = date.today()
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        prox = {d: (hoy + timedelta(days=(i - hoy.weekday()) % 7 or 7)).isoformat()
                for i, d in enumerate(dias)}
        return ("FECHAS (para resolver lo que diga el usuario):\n"
                f"  hoy = {hoy.isoformat()} ({dias[hoy.weekday()]})\n"
                f"  mañana = {(hoy + timedelta(days=1)).isoformat()}\n"
                + "".join(f"  próximo {d} = {f}\n" for d, f in prox.items()))

    @staticmethod
    def _fecha_de(dia: object) -> str | None:
        """'hoy' | 'mañana' | un día de la semana → AAAA-MM-DD, resuelto aquí (no por el
        modelo). Un día de la semana es el PRÓXIMO: si hoy es ese mismo día, el de hoy."""
        if not isinstance(dia, str) or not dia.strip():
            return None
        d = dia.strip().lower()
        hoy = date.today()
        if d in ("hoy", "today"):
            return hoy.isoformat()
        if d in ("mañana", "manana", "tomorrow"):
            return (hoy + timedelta(days=1)).isoformat()
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        equivale = {"miercoles": "miércoles", "sabado": "sábado"}
        d = equivale.get(d, d)
        if d not in dias:
            return None
        return (hoy + timedelta(days=(dias.index(d) - hoy.weekday()) % 7)).isoformat()

    def system(self) -> str:
        return SYSTEM + "\n\n" + self._contexto_fechas() + self._limites_extra()

    def _limites_extra(self) -> str:
        """Los límites que la clínica le escribe en Config › Agentes IA, para el prompt.

        Se escribían y no llegaban al modelo: la lista se guardaba y nadie la leía. Sin
        config valen los del catálogo."""
        from application.services.agente_service import AgenteService
        return AgenteService(self.s)._limites_centro(self.centro_id, "victor")

    # Permiso de la app (Config › Agentes IA) que exige cada herramienta de Victor. Mismo
    # catálogo de 4 permisos combinables que Alex (agente_service.PERMISOS_AGENTE).
    PERMISO_DE_TOOL = {
        "resumen_dia": "citas.ver",
        "pacientes_sin_venir": "pacientes.ver",
        "bloquear_agenda": "citas.editar",
    }

    def _permisos_concedidos(self) -> set[str]:
        from application.services.agente_service import PERMISOS_AGENTE
        from application.services.config_service import ConfigService
        from domain.config.agentes import POR_ID
        cfg = ConfigService(self.s).resolve(self.config_key, centro_id=self.centro_id,
                                            sistema=self.config_sistema, default=None) or {}
        req = (cfg.get("permisos") or {}).get("requiere") if isinstance(cfg, dict) else None
        if not isinstance(req, list):
            req = POR_ID["victor"].permisos
        return {p for p in req if p in PERMISOS_AGENTE}

    def herramientas(self) -> list[dict]:
        """Las de sus capacidades que además permitan sus permisos de la app."""
        return self._herramientas_permitidas(self._herramientas_por_capacidad())

    def _herramientas_permitidas(self, tools: list[dict]) -> list[dict]:
        """Filtra una lista de herramientas por los permisos concedidos a Victor.

        Separado de `herramientas()` para poder filtrar cualquier lista (la del roster de la
        BD, la del catálogo, la de un test) con el mismo criterio, en vez de repetir la
        comprobación en cada sitio y que se desincronicen. Una herramienta sin permiso
        asociado pasa: el mapa cubre las que tocan datos."""
        concedidos = self._permisos_concedidos()
        return [t for t in tools
                if self.PERMISO_DE_TOOL.get(t["function"]["name"]) in (None, *concedidos)]

    def _herramientas_por_capacidad(self) -> list[dict]:
        from application.services.capacidades_service import herramientas_base

        tools = herramientas_base(self.s, self.centro_id, "staff")
        if tools:
            # La BD dice CUÁLES; la definición (descripción y parámetros) es la de TOOLS: la de
            # BD llega con parameters={} y Ollama la rechaza ("properties must be an object").
            _def = {t["function"]["name"]: t for t in TOOLS}
            tools = [_def[t["function"]["name"]] for t in tools if t["function"]["name"] in _def]
            if tools:
                return tools
        return TOOLS

    def ejecutar(self, nombre: str, args: dict) -> str:
        """Despacha la herramienta al servicio.

        Clave de seguridad: `bloquear_agenda` se fuerza SIEMPRE a modo previsualización
        (confirmar=False), pase lo que pase por los argumentos. El LLM no tiene forma de
        ejecutar un cambio: aunque 'quisiera' confirmarlo, aquí no se le deja. La ejecución
        real es un botón que pulsa una persona (endpoint aparte). Es lo que falló en la
        primera versión: el modelo se auto-confirmó y bloqueó una agenda sin permiso."""
        try:
            if nombre == "bloquear_agenda":
                r = self.svc.bloquear_agenda(
                    args.get("doctor", ""), args.get("fecha", ""),
                    motivo=args.get("motivo", ""), desde=args.get("desde"),
                    hasta=args.get("hasta"), confirmar=False)   # NUNCA True desde el LLM
                # Si la previsualización es válida, se guarda como acción pendiente de un clic.
                if r.get("ok") and r.get("confirmado") is False:
                    self.pendientes.append({"accion": "bloquear_agenda",
                                            "args": {k: args.get(k) for k in
                                                     ("doctor", "fecha", "desde", "hasta", "motivo")},
                                            "resumen": r.get("resumen"),
                                            "citasAfectadas": r.get("citasAfectadas")})
            elif nombre == "pacientes_sin_venir":
                r = self.svc.pacientes_sin_venir(int(args.get("meses", 12)), limite=50)
            elif nombre == "resumen_dia":
                # `dia` manda sobre `fecha`: el modelo acertaba la fecha solo a veces (dijo
                # "el lunes (20 de octubre)" con el lunes 19), así que la resuelve la web.
                r = self.svc.resumen_dia(self._fecha_de(args.get("dia")) or args.get("fecha"))
            else:
                r = {"error": f"herramienta desconocida: {nombre}"}
        except Exception as e:  # raiz: error de herramienta vuelve al LLM, no tumba la conversación
            r = {"error": str(e)}
        return json.dumps(r, ensure_ascii=False)

    def extra(self) -> dict:
        # Acciones que el usuario puede confirmar con un botón (nunca se ejecutan solas).
        return {"accionesPendientes": self.pendientes}
