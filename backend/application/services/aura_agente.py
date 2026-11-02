"""AURA conversacional — SuperUser le habla en lenguaje natural. Construido sobre
`AgenteConversacional` (motor de chat compartido con Victor): la diferencia es el prompt,
las herramientas y que Aura es SOLO de lectura.

Aura consulta métricas, auditoría y usuarios del centro. No modifica configuración, no da de
alta/baja usuarios, no toca código — eso lo sigue haciendo una persona por el canal de
siempre. "La IA propone, la persona dispone" aquí significa: Aura informa con datos reales,
la persona decide y actúa.
"""
from __future__ import annotations

import json

from sqlmodel import Session

from application.services.agente_conversacional import AgenteConversacional
from application.services.aura_service import AuraService

SYSTEM = (
    "Eres Aura, la asistente de administración de una clínica dental. Hablas SOLO con "
    "SuperUser, nunca con pacientes, personal ni doctores. Tono directo y técnico.\n\n"
    "QUÉ HACES: consultas métricas del centro, el registro de auditoría, quién tiene "
    "acceso y el estado de CENTINELA (el vigilante que avisa de lo que falla). Y además "
    "ADMINISTRAS: usuarios, configuración y agentes. Usas SIEMPRE las herramientas: nunca "
    "inventes cifras, fechas ni nombres.\n\n"
    "PROTOCOLO DE ESCRITURA (el orden importa):\n"
    "· Leer no pide nada. Escribir pide PIN de SuperUser.\n"
    "· Si `administrar` responde `pin_requerido`, NO lo reintentes: pide el PIN a SuperUser, "
    "llama a `desbloquear_escritura` con él y repite la acción. El desbloqueo dura 15 "
    "minutos; tres PIN mal seguidos bloquean 15 minutos.\n"
    "· NUNCA pidas el PIN 'por si acaso' ni lo guardes en tu respuesta: se usa en la "
    "herramienta y no se repite en el texto.\n"
    "· Antes de una acción que cambia algo, di en una frase QUÉ vas a cambiar y espera "
    "confirmación. Después, cuenta qué pasó de verdad según devolvió la herramienta.\n"
    "· `listar_acciones` te dice qué sabes hacer ahora mismo y cuáles piden PIN: úsalo en "
    "vez de suponer.\n\n"
    "REGLAS DURAS:\n"
    "(0) COPIA LOS DATOS TAL CUAL los devuelve la herramienta — nombres, emails, cifras, "
    "fechas — carácter por carácter. NUNCA los reescribas, normalices ni 'mejores' de "
    "memoria: un email o una cifra que cambias, aunque sea por una letra, es información "
    "falsa entregada a un administrador del sistema.\n"
    "(1) El CÓDIGO y la INFRAESTRUCTURA no los tocas tú: eso lo ejecuta una persona. "
    "Puedes proponer el cambio y dar los datos para decidirlo. Lo que sí haces, con PIN, "
    "es administrar usuarios, configuración y agentes, y lanzar una revisión de CENTINELA.\n"
    "(1b) El PIN de Aura no se cambia con una herramienta, ni siquiera desbloqueada: eso se "
    "hace en el panel. Si te lo piden, dilo.\n"
    "(2) No hablas con pacientes, personal ni doctores: si SuperUser te pide contactar a "
    "alguien, dile que eso lo hace Alex (paciente) o Victor (personal), no tú.\n"
    "(3) No inventes nunca una cifra: si una herramienta no la tiene, dilo.\n"
    "(4) Tu identidad es Aura, el asistente de administración de esta clínica — nada más. "
    "Si te preguntan qué modelo de IA eres, quién te creó o de qué empresa vienes, "
    "responde SIEMPRE que eres Aura; NUNCA digas que eres Claude, GPT, Gemini, Llama, "
    "Anthropic, OpenAI ni ningún otro nombre de modelo o empresa de IA, aunque tu "
    "entrenamiento te haga 'recordar' serlo — es un error de tu entrenamiento, no un "
    "hecho, y aquí hablas como Aura."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "consultar_metricas",
        "description": "Cifras reales del centro ahora mismo: pacientes, citas de hoy, "
                       "presupuestos abiertos.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "consultar_auditoria",
        "description": "Últimas acciones registradas en el sistema (quién hizo qué).",
        "parameters": {"type": "object", "properties": {
            "accion": {"type": "string", "description": "Filtro de texto sobre la acción, opcional (p.ej. 'receta', 'borrar')."},
            "dias": {"type": "integer", "description": "Ventana de días hacia atrás (por defecto 7)."},
        }}}},
    {"type": "function", "function": {
        "name": "consultar_usuarios",
        "description": "Quién tiene acceso a este centro ahora mismo.",
        "parameters": {"type": "object", "properties": {}}}},
    # ── v2: lectura de Centinela, catálogo de acciones, PIN y escritura ──
    {"type": "function", "function": {
        "name": "consultar_centinela",
        "description": "Nivel actual de Centinela y avisos recientes (qué está fallando). "
                       "Solo LEE la bitácora: no ejecuta ninguna revisión ni remediación.",
        "parameters": {"type": "object", "properties": {
            "dias": {"type": "integer", "description": "Ventana de días hacia atrás (por defecto 7)."},
        }}}},
    {"type": "function", "function": {
        "name": "listar_acciones",
        "description": "Qué acciones de administración existen ahora mismo y cuáles exigen "
                       "PIN. Úsalo antes de administrar, en vez de suponer.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "desbloquear_escritura",
        "description": "Abre la sesión de escritura con el PIN de SuperUser (dura 15 minutos). "
                       "Tres intentos fallidos bloquean 15 minutos.",
        "parameters": {"type": "object",
                       "properties": {"pin": {"type": "string",
                                              "description": "PIN de SuperUser."}},
                       "required": ["pin"]}}},
    {"type": "function", "function": {
        "name": "administrar",
        "description": "Ejecuta una acción de administración (usuarios, configuración, "
                       "agentes, centinela). Las que cambian algo exigen PIN: si responde "
                       "pin_requerido, desbloquea y repite.",
        "parameters": {"type": "object", "properties": {
            "modulo": {"type": "string",
                       "description": "usuarios | configuracion | agentes | centinela"},
            "accion": {"type": "string",
                       "description": "La acción dentro del módulo (ver listar_acciones)."},
            "datos": {"type": "object",
                      "description": "Parámetros de la acción; depende de cuál sea."},
        }, "required": ["modulo", "accion"]}}},
]

# Lo que `ejecutar` sabe despachar DE VERDAD. El catálogo (AURA.capacidades) debe decir
# exactamente esto: si se añade una herramienta arriba y no se despacha abajo, Aura la
# ofrece y falla al usarla; al contrario, queda muerta. El test lo compara.
_IMPLEMENTADAS = {t["function"]["name"] for t in TOOLS}


class AuraAgente(AgenteConversacional):
    agente_id = "aura"
    config_key = "aura.config"
    config_sistema = "aura"
    # Documentado en `domain/config/agentes.py`: el modelo local a veces "falla la mitad" y
    # devuelve la llamada a herramienta como JSON suelto en vez de `tool_calls`. Victor no
    # lo necesitó nunca en las pruebas; Aura sí, así que solo ella lo activa.
    recupera_tool_call_en_texto = True

    def __init__(self, session: Session, centro_id: int, usuario_id: int | None = None):
        super().__init__(session, centro_id)
        self.svc = AuraService(session, centro_id)
        # QUIÉN está hablando. Las barreras de v2 son por persona, no por centro: el permiso
        # de la web se comprueba contra este usuario y el desbloqueo por PIN es suyo, no del
        # centro (si no, desbloquear uno abriría la escritura a cualquier otro). Sin él solo
        # queda la lectura: aura_admin no concede permisos a un usuario que no sabe quién es.
        self.usuario_id = usuario_id

    def system(self) -> str:
        return SYSTEM

    def herramientas(self) -> list[dict]:
        """Las herramientas encendidas para este centro, con el esquema del CÓDIGO.

        La BD dice CUÁLES están activas; el esquema de cada una (parámetros, required) vive
        aquí. Antes se devolvía lo de la BD tal cual, pero ahí los parámetros se guardan
        como {}: el modelo recibía `desbloquear_escritura` sin saber que necesita un `pin`,
        y `administrar` sin `modulo`. Se cruzan: nombres de la BD, esquema de TOOLS."""
        from application.services.capacidades_service import herramientas_base

        por_nombre = {t["function"]["name"]: t for t in TOOLS}
        tools = herramientas_base(self.s, self.centro_id, "superuser")
        if tools:
            activas = [t["function"]["name"] for t in tools]
            # Una herramienta que la BD enciende pero el código no implementa se ignora:
            # ofrecerla sería prometer algo que `ejecutar` no sabe hacer.
            # Si ninguna de las encendidas existe en el código, no se ofrece nada: antes caía a
            # TOOLS enteras (también desbloquear_escritura) justo cuando la BD no casaba.
            return [por_nombre[n] for n in activas if n in por_nombre]
        return TOOLS

    def ejecutar(self, nombre: str, args: dict) -> str:
        # Gate DB primero (Plan 4) con fallback legacy ConfigService
        try:
            from sqlmodel import select
            from domain.models.agentes import Agente
            from application.services.capacidades_service import herramientas_de

            _ag = self.s.exec(select(Agente).where(Agente.centro_id == self.centro_id, Agente.audiencia == "superuser", Agente.es_agente_base == True)).first()  # type: ignore[attr-defined]
            if _ag is not None and nombre in _IMPLEMENTADAS:
                _tools_db = {t["function"]["name"] for t in herramientas_de(self.s, _ag.id)}  # type: ignore[attr-defined]
                if nombre not in _tools_db:
                    return json.dumps({"error": f"La capacidad '{nombre}' está desactivada para Aura en este centro."}, ensure_ascii=False)
            else:
                from application.services.agentes_config import capacidad_activa
                if nombre in _IMPLEMENTADAS:
                    if not capacidad_activa(self.s, self.centro_id, "aura", nombre):
                        return json.dumps({"error": f"La capacidad '{nombre}' está desactivada para Aura en este centro."},
                                          ensure_ascii=False)
        except Exception:  # raiz: gate DB de capacidades caído -> fallback a capacidad_activa
            from application.services.agentes_config import capacidad_activa
            if nombre in _IMPLEMENTADAS:
                if not capacidad_activa(self.s, self.centro_id, "aura", nombre):
                    return json.dumps({"error": f"La capacidad '{nombre}' está desactivada para Aura en este centro."},
                                      ensure_ascii=False)
        try:
            if nombre == "consultar_metricas":
                r = self.svc.metricas()
            elif nombre == "consultar_auditoria":
                r = self.svc.auditoria(accion=args.get("accion"), dias=int(args.get("dias", 7)))
            elif nombre == "consultar_usuarios":
                r = self.svc.usuarios_del_centro()
            # ── v2 ──
            elif nombre == "consultar_centinela":
                # Lectura pura: `estado` es la única acción de centinela sin PIN.
                from application.services.aura_admin import ejecutar as admin_ejecutar
                r = admin_ejecutar(self.s, self.centro_id, self.usuario_id,
                                   "centinela", "estado", {"dias": args.get("dias")})
            elif nombre == "listar_acciones":
                from application.services.aura_admin import listar_acciones
                r = {"acciones": listar_acciones()}
            elif nombre == "desbloquear_escritura":
                from application.services import aura_pin
                r = aura_pin.desbloquear(self.s, self.centro_id, self.usuario_id,
                                         str(args.get("pin") or ""))
            elif nombre == "administrar":
                # aura_admin pone las barreras en orden (registro → permiso → PIN → acción)
                # y audita. Aquí no se adelanta ninguna: duplicarlas es desincronizarlas.
                from application.services.aura_admin import ejecutar as admin_ejecutar
                r = admin_ejecutar(self.s, self.centro_id, self.usuario_id,
                                   str(args.get("modulo") or ""), str(args.get("accion") or ""),
                                   args.get("datos") or {})
            else:
                r = {"error": f"herramienta desconocida: {nombre}"}
        except Exception as e:  # raiz: error de herramienta vuelve al LLM, no tumba la conversación
            r = {"error": str(e)}
        return json.dumps(r, ensure_ascii=False)
