"""Configuración de cada agente: la crea y la lee, derivada del CATÁLOGO.

Por qué existe: la config de los agentes se había ido escribiendo a mano, cada una con una
forma distinta (`aura.config` era literalmente `{"activa": false}` mientras `gestor.config`
tenía capacidades, permisos y límites). Y `agente.victor` no existía siquiera, aunque el
roster lo define. Aquí se genera desde `domain/config/agentes.py`, así que la lista de
capacidades NO se escribe dos veces: si mañana Victor gana una herramienta, aparece sola.

Lo que decide el usuario y esta función respeta:
  · `activa`      → el agente se puede apagar; apagado NO es avería.
  · `capacidades` → cada una on/off por separado (Victor puede leer informes pero no
                    bloquear agendas, si así se quiere).
  · `limites`     → topes numéricos propios de cada agente.
Al reconciliar, lo que ya haya elegido el usuario MANDA: sólo se añade lo que falta.
"""
from __future__ import annotations

from typing import Any

from sqlmodel import Session

from application.services.config_service import ConfigService
from application.services.llm_config import resolver_llm
from domain.config.agentes import CATALOGO, POR_ID

# En qué "sistema" de CONFIG vive la clave de cada agente (así lo lee ya el frontend).
SISTEMA = {"agente.alex": "ia", "agente.victor": "ia", "aura.config": "aura",
           "gestor.config": "gestor"}

# Topes de los límites que el usuario escribe a mano (PATCH /agentes/{id}/config y Aura).
# Existen para que un límite no se convierta en un prompt entero: el texto va al system del
# agente, así que sin tope se podría empujar ahí lo que fuera. El router y aura_admin los
# importaban ya; faltaba definirlos aquí, y por eso el endpoint rompía al guardar límites.
MAX_LIMITES = 20
MAX_LIMITE_CHARS = 200


def sanitizar_limites(valor: Any) -> list[str]:
    """Deja una lista de límites utilizable: descarta lo que no sea texto con contenido,
    recorta espacios y aplica los topes. Lo que no es lista NO es un error del usuario que
    merezca un 500: es «no me has dado límites» → []."""
    if not isinstance(valor, list):
        return []
    limpios = [x.strip() for x in valor if isinstance(x, str) and x.strip()]
    return [x[:MAX_LIMITE_CHARS] for x in limpios[:MAX_LIMITES]]


def limites_de(config: dict[str, Any] | None, agente_id: str) -> list[str]:
    """Límites en vigor de un agente. Sin configurar → los del CATÁLOGO (el agente nunca
    queda sin límites por un descuido). Una lista vacía puesta a mano SÍ se respeta: es una
    decisión del usuario, no una ausencia."""
    if isinstance(config, dict) and config.get("limites_texto") is not None:
        return sanitizar_limites(config["limites_texto"])
    return list(POR_ID[agente_id].limites)


def permisos_efectivos(config: dict[str, Any] | None, agente_id: str) -> list[str]:
    """Permisos de la app en vigor. Mismo criterio que los límites: si nadie los ha tocado
    valen los del catálogo, y se ignora lo que no sea texto."""
    if isinstance(config, dict):
        req = (config.get("permisos") or {}).get("requiere")
        if isinstance(req, list):
            return [x for x in req if isinstance(x, str)]
    return list(POR_ID[agente_id].permisos)


def herramienta_permitida(permisos: list[str], agente_id: str, herramienta: str) -> bool:
    """¿Puede este agente usar esta herramienta con los permisos que tiene concedidos?

    Una herramienta sin permiso asociado en el mapa NO se bloquea: el mapa cubre las que
    tocan datos (agenda, pacientes), y lo que no está ahí no abre nada que haya que gatear.
    Negar por defecto dejaría mudo al agente cada vez que se añade una herramienta nueva."""
    from application.services.agente_service import PERMISO_DE_TOOL
    if agente_id not in POR_ID:
        return True
    necesario = PERMISO_DE_TOOL.get(herramienta)
    return necesario is None or necesario in (permisos or [])


def plantilla(agente_id: str) -> dict[str, Any]:
    """Config por defecto de un agente, derivada del catálogo. Arranca DESACTIVADO.

    Se entrega apagado a propósito: un agente que empieza a hablar con pacientes o a tocar
    agendas el día que se despliega, sin que nadie lo haya encendido, es un accidente.

    El campo `modelo` es solo informativo (registra qué modelo tenía el catálogo el día en
    que se activó): NO es lo que decide qué modelo usa el agente en cada llamada real — eso
    lo resuelve `resolver_llm()` contra `Integracion(tipo=llm)`. `estado()`, más abajo, lee
    de ahí, no de este campo, precisamente para no volver a quedarse con un valor congelado."""
    a = POR_ID[agente_id]
    return {
        "activa": False,
        "modelo": a.modelo,
        # Todas las capacidades del catálogo, apagadas salvo las de sólo lectura: consultar
        # no cambia nada, así que puede venir activo; escribir lo enciende una persona.
        "capacidades": {k: k.startswith(("consultar", "informe", "resumen", "buscar",
                                         "preparar", "verificar", "extraer", "transcribir"))
                        for k in a.capacidades},
        "permisos": {"requiere": a.permisos, "modo_accion": "confirmar", "auditoria": True},
        "limites": {"max_acciones_hora": 60},
        # Los límites del catálogo, en texto, para que entren en el prompt del agente. Antes
        # esta lista era decorativa: se mostraba en la pantalla y NADIE la metía en el
        # system, así que un límite escrito por la clínica no llegaba nunca al modelo.
        "limites_texto": list(a.limites),
    }


def reconciliar(session: Session, centro_id: int) -> dict:
    """Asegura que TODOS los agentes del catálogo tienen su config, sin pisar lo elegido.

    Idempotente: se puede llamar en cada arranque. Añade claves nuevas (una capacidad que
    no existía) conservando el valor que el usuario haya puesto en las que ya estaban."""
    cfg = ConfigService(session)
    resultado = {"creadas": [], "completadas": [], "intactas": []}

    for a in CATALOGO:
        clave = a.config_key
        sistema = SISTEMA.get(clave, "ia")
        actual = cfg.resolve(clave, centro_id=centro_id, sistema=sistema, default=None)
        base = plantilla(a.id)

        if not actual:
            cfg.set(clave, base, centro_id=centro_id, sistema=sistema)
            resultado["creadas"].append(clave)
            continue

        # Mezcla conservadora: lo que hay gana; sólo se rellenan los huecos.
        cambiado = False
        fusion = {**base, **actual}
        for bloque in ("capacidades", "permisos", "limites"):
            mezcla = {**base.get(bloque, {}), **(actual.get(bloque) or {})}
            if mezcla != (actual.get(bloque) or {}):
                cambiado = True
            fusion[bloque] = mezcla
        # El modelo lo manda el catálogo salvo que el centro lo haya cambiado a mano. Es
        # solo el valor que se muestra si `resolver_llm()` no tiene nada mejor (ver estado()).
        if "modelo" not in actual:
            fusion["modelo"] = base["modelo"]
            cambiado = True
        # Los límites en texto son una LISTA, así que la mezcla por bloques de arriba (que
        # recorre dicts) no los cubre. Se siembran solo si la clave no está: una lista vacía
        # puesta a mano es una decisión del usuario y se respeta.
        if "limites_texto" not in actual:
            fusion["limites_texto"] = base["limites_texto"]
            cambiado = True

        if cambiado:
            cfg.set(clave, fusion, centro_id=centro_id, sistema=sistema)
            resultado["completadas"].append(clave)
        else:
            resultado["intactas"].append(clave)
    return resultado


def capacidad_activa(session: Session, centro_id: int, agente_id: str, capacidad: str) -> bool:
    """¿Puede `agente_id` usar `capacidad` ahora mismo? Comprueba activa+operativa del
    agente Y el interruptor de esa capacidad concreta — los tres tienen que estar en verde.

    Por qué existe: el interruptor de capacidad en Config·Agentes IA·Catálogo escribía en
    config pero nada lo leía al ejecutar la herramienta — apagar "consultar_auditoria" en
    la pantalla no impedía que Aura la usara igual. Cualquier `ejecutar()` de un agente debe
    llamar aquí antes de correr una herramienta que tenga capacidad asociada."""
    a = POR_ID.get(agente_id)
    if not a or capacidad not in a.capacidades:
        return False
    filas = estado(session, centro_id)
    fila = next((f for f in filas if f["id"] == agente_id), None)
    if not fila or not fila["operativa"]:
        return False
    return capacidad in fila["capacidadesActivas"]


def estado(session: Session, centro_id: int) -> list[dict]:
    """Estado de cada agente: encendido, modelo, capacidades vivas y jerarquía.

    Ningún agente del catálogo actual depende de otro (Victor → personal de clínica, Aura →
    SuperUser: ámbitos independientes) — `depende_de` queda como mecanismo genérico por si
    algún agente futuro sí lo necesita. Se distingue `activa` (su interruptor) de `operativa`
    (si de verdad va a funcionar): si algún día se añade una dependencia, decir que un
    agente está encendido cuando su responsable está apagado sería mentirle al usuario.

    El `modelo` de cada fila viene de `resolver_llm()` — lo que de verdad usaría el agente en
    su próxima llamada (Integracion tipo=llm, o el catálogo si no hay override, o nada si el
    motor está apagado) — nunca del valor guardado en config, que se escribe una vez y
    `reconciliar()` no vuelve a tocar si ya existe. Antes de esto la tarjeta de un agente
    podía mostrar un modelo (p.ej. de un proveedor externo ya retirado) mientras el agente
    corría de verdad sobre otro (el motor local): un dato de configuración visible y falso."""
    cfg = ConfigService(session)
    propio: dict[str, bool] = {}
    filas = []
    for a in CATALOGO:
        c = cfg.resolve(a.config_key, centro_id=centro_id,
                        sistema=SISTEMA.get(a.config_key, "ia"), default=None) or {}
        caps = c.get("capacidades") or {}
        if a.id == "gestor":
            # `activa` no es de fiar aquí: el watch de Gmail se renueva por cron y puede
            # pararse solo (expira a los 7 días) sin pasar por este flag — mentir "encendido"
            # mientras el pipeline real está muerto es peor que una llamada de más.
            from infrastructure.external_apis import gmail_watch
            propio[a.id] = bool(gmail_watch.estado_watch(session, centro_id).get("activo"))
        else:
            propio[a.id] = bool(c.get("activa"))
        # SOLO capacidades del catálogo: la config puede arrastrar claves legado
        # (informar_cita, escalar_humano…) que ya no existen. Contarlas daba "13/11".
        activas = sorted(k for k in a.capacidades if caps.get(k))
        real = resolver_llm(session, centro_id, a.id)
        modelo = (real or {}).get("model") or a.modelo
        # Dato de CONEXIÓN real (a qué proveedor habla el agente ahora mismo), no el modelo
        # "de catálogo": si no hay Integracion activa, no hay conexión — decirlo, no inventar.
        base_url = (real or {}).get("base_url") or None
        suplentes: list[str] = []
        from domain.config.settings import settings
        from infrastructure.external_apis.jarvis_operador import AGENTES_POR_JARVIS, modelo_jarvis
        if settings.jarvis_operador_url and a.id in AGENTES_POR_JARVIS:
            # Contesta su operador de Jarvis: el modelo es el de Jarvis (y, si .117 falla, los
            # suplentes del relé de la web), no el de esta web ni el del catálogo.
            m = modelo_jarvis()
            modelo = f"{m} (Jarvis)" if m else "Jarvis (no responde)"
            base_url = settings.jarvis_operador_url
            from application.services.llm_config import motor_compartido
            suplentes = [f"{r.get('nombre')}: {r.get('model')}"
                         for r in ((motor_compartido(session) or {}).get("relevos") or [])
                         if isinstance(r, dict) and r.get("model")]
        filas.append({
            "id": a.id, "nombre": a.nombre, "titular": a.titular,
            "activa": propio[a.id],
            "modelo": modelo,
            "baseUrl": base_url,
            "suplentes": suplentes,
            "capacidadesActivas": activas,
            "capacidadesTotales": len(a.capacidades),
            "configKey": a.config_key,
            "dependeDe": a.depende_de,
        })
    for f in filas:
        jefe = f["dependeDe"]
        f["operativa"] = f["activa"] and (propio.get(jefe, True) if jefe else True)
        f["bloqueadoPor"] = (POR_ID[jefe].nombre
                             if jefe and f["activa"] and not propio.get(jefe, True) else None)
    return filas
