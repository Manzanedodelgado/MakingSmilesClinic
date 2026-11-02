"""CATÁLOGO DE AGENTES — la fuente ÚNICA de verdad de quién es quién en el área de IAs.

Antes de este fichero había dos rosters incompatibles conviviendo: el del modelo de datos
(AURA/VISTA/ESCUCHA/PLUMA/FORENSE, tablas vacías que ningún código tocaba) y el de la UI
(Alex/Victor/Gestor). Nadie sabía de qué se hablaba. Aquí queda uno solo, y el resto del
sistema —config, permisos, elección de modelo, pantallas— lee de aquí.

Las cinco parcelas, sin solapamiento:

    ALEX                habla con el PACIENTE          (fuera → dentro: WhatsApp y voz)
    VICTOR              habla con el PERSONAL/EQUIPO   (dentro: agenda, informes, pacientes,
                                                         Y lo que pasa en la consulta: escucha,
                                                         transcribe y extrae el SOAP)
    AURA                habla con el SUPERUSER         (dentro: administración total del sistema)
    GESTOR              facturas, contabilidad y conciliación bancaria

Victor y Aura son independientes entre sí (ámbitos distintos: personal de clínica vs.
SuperUser) — ninguno depende del otro para operar.

GESTOR fusiona lo que antes eran dos agentes ("Gestor IA" + "Gestor IA Multimodal"). Eran
la misma función de negocio (procesar facturas) descrita dos veces: el primero decía "lee el
buzón y extrae los datos" pero ese código se borró hace tiempo (ver `gmail_ingest_service.py`,
que ya solo hace config/visor/Drive — la ingesta real vive en `gmail_ai_processor.py`, el
webhook de Gmail). Y el interruptor de "Gestor IA Multimodal" en la pantalla no apagaba nada
real: el encendido de verdad es la suscripción push de Gmail (`gmail_watch.py`), un sistema
aparte que el toggle nunca tocaba. Un solo agente, un solo interruptor, conectado al real.

CENTINELA no está aquí a propósito: no es un agente conversacional, es la vigilancia de la
salud del sistema (backend, BD, disco, errores). Vive en `centinela.config` y se configura
por su lado; meterlo en este catálogo sería repetir la confusión que este fichero deshace.

Principio heredado y no negociable: la IA propone, la persona dispone.
"""
from __future__ import annotations

from typing import Optional

# ─────────────────────────── MODELOS ───────────────────────────
# Medidos EN VIVO contra el catálogo real de NVIDIA (24-jul-2026), no elegidos por catálogo:
# se comprobó que responden, que aceptan `tools` (function calling) y cuánto tardan.
#
#   openai/gpt-oss-20b            1,0 s   tools OK   → conversación en vivo
#   meta/llama-3.3-70b-instruct   5,4 s   tools OK   → razonamiento y textos largos
#   qwen/qwen3-next-80b-a3b       40,3 s  tools OK   → descartado: inservible en conversación
#   mistral-nemotron                 —    SIN tools  → descartado: los agentes usan herramientas
#   nemotron-70b/ultra, mistral-large-2, gemma-3   → 404, no servidos en este endpoint
#
# El modelo anterior (mistralai/mistral-large-3-675b-instruct-2512) fue RETIRADO por NVIDIA
# el 23-jul-2026 (HTTP 410 Gone) y dejó toda la IA de texto muerta sin que nada avisara.
# Modelo de Alex: elegido por FIABILIDAD, no por velocidad pura. Medido en vivo (25-jul-2026)
# sobre el caso real "dolor de muela de noche → cita + consejos" (encadena herramientas):
#   openai/gpt-oss-20b    2,6 s/turno · 3/6 OK  → RÁPIDO pero falla la mitad (escala o se cuelga)
#   openai/gpt-oss-120b   13 s/turno  · 5/5 OK  → fiable; aceptable en WhatsApp (medio asíncrono)
#   meta/llama-3.3-70b    23 s/turno  · 6/6 OK  → demasiado lento para chat en vivo
# Con un paciente al otro lado, una respuesta correcta en 13 s > una basura en 2 s.
#
# Desde el 30-ago-2026 Alex/Victor/Aura/Gestor corren sobre un único motor LOCAL (Ollama,
# RTX 3080 de PC-ESCANER, compartido con el escáner Medit i500 — interruptor manual en
# Config·Agentes IA) por coste: hoy ALEX_MODELO y CAPAZ apuntan al mismo modelo porque solo
# hay uno descargado. Cuando haya más de uno, la distinción de fiabilidad de arriba vuelve
# a aplicar y estas constantes divergen de nuevo.
#
# 18-oct-2026: era `qwen2.5-coder:7b`, un modelo DE PROGRAMAR que ya no está en la GPU y que
# este catálogo imponía por encima de la integración compartida. Alex/Victor/Aura contestan
# por su operador de Jarvis (que usa qwen3.5-clinica), así que no se notaba, pero era el
# modelo al que caerían sin Jarvis y el que usaba el Gestor. Ahora es el mismo que usan
# Jarvis y Hermes: un solo modelo cargado en la GPU.
ALEX_MODELO = "qwen3.5-clinica:latest"
CAPAZ = "qwen3.5-clinica:latest"  # informes, extracción clínica, análisis (Victor/Aura/Gestor)


class Agente:
    """Una parcela de IA: qué hace, dónde puede tocar y con qué modelo piensa."""

    def __init__(self, *, id: str, nombre: str, titular: str, parcela: str,
                 modelo: str, permisos: list[str], capacidades: dict[str, str],
                 limites: list[str], config_key: str, requiere: Optional[list[str]] = None,
                 depende_de: Optional[str] = None,
                 permisos_tools: Optional[dict[str, str]] = None):
        self.id = id
        self.nombre = nombre
        self.titular = titular          # con QUIÉN habla (paciente / doctor / nadie)
        self.parcela = parcela          # DÓNDE actúa, en una frase
        self.modelo = modelo            # modelo por defecto (se puede pisar por centro)
        self.permisos = permisos        # permisos de la app que necesita para operar
        self.capacidades = capacidades  # qué sabe hacer → descripción para la UI
        self.limites = limites          # qué NO puede hacer (frontera explícita)
        self.config_key = config_key    # clave en `configuraciones` donde vive su on/off
        self.requiere = requiere or []  # dependencias externas sin las que no funciona
        # Agente del que depende. NO es decoración: si el responsable está apagado, el
        # subordinado tampoco opera. Ningún agente del catálogo actual depende de otro
        # (Victor → personal, Aura → SuperUser: ámbitos independientes) — se conserva como
        # mecanismo genérico por si algún agente futuro sí necesita depender de otro.
        self.depende_de = depende_de
        # Qué permiso de la app exige CADA capacidad, una a una. `permisos` dice lo que el
        # agente necesita en conjunto; esto dice cuál hace falta para cada herramienta, que es
        # lo que permite negar una sola sin apagar al agente entero. Vacío = ninguna
        # herramienta está gateada por permiso (el caso de los agentes cuyo gate es la
        # capacidad on/off, no el permiso).
        self.permisos_tools = permisos_tools or {}

    def to_dict(self) -> dict:
        return {"id": self.id, "nombre": self.nombre, "titular": self.titular,
                "parcela": self.parcela, "modelo": self.modelo, "permisos": self.permisos,
                "capacidades": self.capacidades, "limites": self.limites,
                "configKey": self.config_key, "requiere": self.requiere,
                "dependeDe": self.depende_de, "permisosTools": self.permisos_tools}


ALEX = Agente(
    id="alex",
    nombre="Alex",
    titular="El paciente",
    parcela="Relación con el paciente por WhatsApp y voz. Es la cara de la clínica hacia fuera.",
    modelo=ALEX_MODELO,
    # pacientes.editar entra porque `crear_presupuesto` (capacidad real de Alex, solo staff)
    # escribe en la ficha del paciente. Faltaba, y el permiso que esa herramienta exige
    # quedaba fuera de la lista: no se podía conceder lo que hacía falta para usarla.
    permisos=["comunicacion.ver", "comunicacion.editar", "pacientes.ver", "pacientes.editar",
              "citas.ver", "citas.editar"],
    # Claves reales comprobadas por CAP_DE_TOOL en application/services/agente_service.py —
    # cada una gatea de verdad una o varias herramientas del LLM (_tools_para). Si la clave no
    # está aquí, PATCH /agentes/alex/config la rechaza con "no es una capacidad de Alex": este
    # dict NO es decorativo, es la lista blanca que el backend comprueba de verdad.
    # verificar_identidad y consultar_disponibilidad quedan fuera a propósito: no tienen
    # entrada en CAP_DE_TOOL, están siempre activas (guarda de identidad / lectura de huecos).
    capacidades={
        "consultar_mis_citas": "Consultar las próximas citas del paciente",
        "consultar_tratamientos_pendientes": "Consultar tratamientos pendientes del paciente",
        "crear_cita": "Crear una cita nueva en un hueco libre",
        "modificar_cita": "Cambiar la fecha/hora de la próxima cita",
        "enviar_presupuesto": "Pedir al equipo que envíe el presupuesto al paciente",
        "enviar_factura": "Pedir al equipo que envíe una factura al paciente",
        "enviar_recibo": "Pedir al equipo que envíe un recibo al paciente",
        "enviar_justificante": "Pedir al equipo un justificante de asistencia",
        "escalar_a_humano": "Avisar a una persona del equipo (urgencia, queja, petición de humano)",
        "crear_presupuesto": "Localizar paciente, resolver tratamientos y crear presupuesto por dictado (solo staff/simulador)",
    },
    limites=[
        "NUNCA revela datos sin verificar identidad con nombre completo",
        "No inventa huecos ni datos: todo sale de las herramientas",
        "No habla con el equipo: eso es de Victor",
        "No toca facturación ni contabilidad: eso es del Gestor",
    ],
    # Qué permiso exige cada herramienta, espejo de PERMISO_DE_TOOL en agente_service. Es lo
    # que permite quitarle la agenda sin apagarlo: sin citas.editar deja de ofrecer y de
    # ejecutar crear/modificar cita, y sigue atendiendo todo lo demás.
    permisos_tools={
        "consultar_disponibilidad": "citas.ver",
        "consultar_mis_citas": "citas.ver",
        "crear_cita": "citas.editar",
        "modificar_cita": "citas.editar",
        # verificar_identidad NO se gatea a propósito: es la guarda que exige el nombre
        # completo antes de soltar ningún dato. Si se pudiera apagar quitando un permiso,
        # quitar un permiso AFLOJARÍA la seguridad en vez de apretarla.
        "consultar_tratamientos_pendientes": "pacientes.ver",
        "enviar_presupuesto": "pacientes.ver",
        "enviar_factura": "pacientes.ver",
        "enviar_recibo": "pacientes.ver",
        "enviar_justificante": "pacientes.ver",
        "buscar_paciente": "pacientes.ver",
        "buscar_tratamientos": "pacientes.ver",
        "crear_presupuesto": "pacientes.editar",
    },
    config_key="agente.alex",
    requiere=["WhatsApp conectado (Evolution)", "modelo con function calling"],
)

VICTOR = Agente(
    id="victor",
    nombre="Victor",
    titular="El personal de la clínica",
    parcela="Agenda, informes y consultas del equipo sobre el centro, y la escucha activa de "
            "la consulta: transcribe y extrae el SOAP para que el doctor no tenga que "
            "teclearlo. Mira hacia dentro, nunca habla con el paciente ni con SuperUser.",
    modelo=CAPAZ,
    # Verificado contra los endpoints reales de api/agentes_router.py: bloquear/liberar
    # agenda exige citas.editar, el informe de pacientes sin venir exige pacientes.ver,
    # y el resumen del día / chat exigen citas.ver.
    permisos=["citas.ver", "citas.editar", "pacientes.ver"],
    # Única clave real: es la que comprueba capacidad_activa(session, centro_id, "victor",
    # "transcribir_consulta") en api/consulta_router.py antes de permitir /consulta/escucha.
    # bloquear_agenda, pacientes_sin_venir y resumen_dia (victor_agente.py) no tienen gate de
    # capacidad — están siempre disponibles si Victor está activo, así que no se listan aquí.
    capacidades={
        "transcribir_consulta": "Escucha activa: transcribe la consulta y extrae el SOAP",
    },
    limites=[
        "No escribe al paciente: si hay que contactar, lo hace Alex o una persona",
        "Toda acción que cambia datos (bloquear agenda) se confirma antes de ejecutar",
        "No entra en facturas ni contabilidad: eso es del Gestor",
        "No administra el sistema ni la configuración: eso es de Aura (SuperUser)",
        "Propone, nunca guarda sola: el doctor revisa y confirma lo de consulta",
    ],
    # Comprobado contra los endpoints reales: bloquear/liberar agenda exigen citas.editar,
    # el informe de quien no ha venido exige pacientes.ver, el resumen del día citas.ver.
    permisos_tools={
        "bloquear_agenda": "citas.editar",
        "liberar_agenda": "citas.editar",
        "pacientes_sin_venir": "pacientes.ver",
        "resumen_dia": "citas.ver",
        "transcribir_consulta": "pacientes.ver",
    },
    config_key="agente.victor",
    # Sin transcripción no hay SOAP. NVIDIA NO ofrece STT en este endpoint (comprobado:
    # solo riva-translate, que traduce texto). Hace falta un motor de voz aparte.
    requiere=["modelo con function calling", "motor de transcripción (STT)"],
)

AURA = Agente(
    id="aura",
    nombre="Aura",
    titular="SuperUser",
    parcela="Administración total del sistema: configuración, usuarios, procesos, "
            "conocimiento, auditoría, análisis técnicos y cambios sobre la propia app. "
            "Habla solo con SuperUser, por chat o WhatsApp.",
    modelo=CAPAZ,
    # Todos los permisos reales del catálogo (`Permiso`) — SuperUser no tiene fronteras
    # de área como el resto de agentes, por diseño.
    permisos=["superuser", "config.ver", "config.editar", "pacientes.ver", "pacientes.editar",
              "citas.ver", "citas.editar", "comunicacion.ver", "comunicacion.editar",
              "gestoria.ver", "gestoria.editar", "gestoria.facturacion.ver",
              "informes.ver", "informes.editar"],
    # Las tres claves reales que comprueba capacidad_activa() en aura_agente.py.ejecutar():
    # antes solo estaba "consultar_metricas" y las otras dos quedaban permanentemente
    # bloqueadas (la comprobación siempre daba False al no existir la clave en el catálogo).
    capacidades={
        "consultar_metricas": "Cifras y estado de cualquier área del sistema",
        "consultar_auditoria": "Últimas acciones registradas en el sistema (quién hizo qué)",
        "consultar_usuarios": "Quién tiene acceso a este centro ahora mismo",
        # v2 (14-oct-2026): Aura deja de ser solo lectura. Estas cuatro son las que hacen
        # falta para eso, y el orden de las barreras importa: permiso de la web PRIMERO,
        # PIN DESPUÉS, auditoría SIEMPRE.
        "consultar_centinela": "Nivel de Centinela y avisos recientes (leer, sin ejecutar nada)",
        "listar_acciones": "Qué sabe hacer Aura ahora mismo y cuáles piden PIN",
        "desbloquear_escritura": "Abrir la sesión de escritura con el PIN de SuperUser (15 min)",
        "administrar": "Ejecutar una acción de administración (usuarios, configuración, agentes, Centinela)",
    },
    # Cada capacidad con el permiso que exige. `administrar` pide superuser porque es la
    # puerta a todo lo demás: el permiso fino lo vuelve a comprobar aura_admin por acción.
    permisos_tools={
        "consultar_metricas": "informes.ver",
        "consultar_auditoria": "superuser",
        "consultar_usuarios": "superuser",
        "consultar_centinela": "superuser",
        "listar_acciones": "superuser",
        "desbloquear_escritura": "superuser",
        "administrar": "superuser",
    },
    limites=[
        "Solo responde a SuperUser: no habla con pacientes, personal ni doctores",
        "Cambios de código/infraestructura los ejecuta un humano, Aura los propone",
        "Nada que escriba se ejecuta sin PIN de SuperUser: sin desbloquear, solo lee",
    ],
    config_key="aura.config",
    requiere=["modelo con function calling"],
)

GESTOR = Agente(
    id="gestor",
    nombre="Gestor IA",
    titular="La gestoría y la administración",
    parcela="Facturas, contabilidad y conciliación bancaria. Procesa cada factura en tiempo "
            "real en cuanto llega por email: la analiza, verifica sus datos y registra el "
            "gasto. Por detrás mantiene la clasificación, la conciliación bancaria y los "
            "avisos de vencimiento.",
    modelo=CAPAZ,
    permisos=["gestoria.ver", "gestoria.editar"],
    capacidades={
        "procesar_email_tiempo_real": "Recibe cada factura al momento por email",
        "verificar_contable": "Valida que los números de la factura cuadren",
        "detectar_inconsistencias": "Avisa de CIF, PDF o destinatario sospechoso",
        "clasificar_gastos": "Asigna categoría y proveedor por CIF",
        "conciliar": "Cuadra apuntes del banco con facturas",
        "detectar_duplicados": "Avisa de facturas repetidas",
        "avisar_vencimientos": "Plazos e impuestos que se acercan",
        "informes": "Cuadros de gasto, IVA e informes para la gestoría",
    },
    limites=[
        "Confianza baja → incidencia para revisión humana (nunca inventa)",
        "Modo sugerencia: por encima del importe configurado, pide confirmación",
        "No toca datos clínicos ni habla con pacientes",
    ],
    # El Gestor no tiene herramientas de LLM gateadas una a una (su trabajo es un flujo que
    # arranca solo al llegar el correo), pero sus capacidades siguen el mismo criterio: leer
    # con gestoria.ver, escribir con gestoria.editar.
    permisos_tools={
        "procesar_email_tiempo_real": "gestoria.editar",
        "verificar_contable": "gestoria.ver",
        "detectar_inconsistencias": "gestoria.ver",
        "clasificar_gastos": "gestoria.editar",
        "conciliar": "gestoria.editar",
        "detectar_duplicados": "gestoria.ver",
        "avisar_vencimientos": "gestoria.ver",
        "informes": "gestoria.ver",
    },
    config_key="gestor.config",
    requiere=["Gmail con watch activo (push)", "Google Drive", "modelo multimodal (Gemini 2.5 Flash)"],
)

CATALOGO: list[Agente] = [ALEX, VICTOR, AURA, GESTOR]
POR_ID: dict[str, Agente] = {a.id: a for a in CATALOGO}
