"""AGENTES DE IA — catálogo, Victor y Aura (capa de interfaz).

Tres bloques:
  · `/agentes`               → el catálogo: quién es quién y qué puede tocar cada uno.
  · `/agentes/victor/…`      → personal de la clínica: agenda, informes, Y la consulta
                                (escuchar y extraer el SOAP).
  · `/agentes/aura/…`        → SuperUser: administración del sistema, solo lectura.

Permisos: cada endpoint exige el de SU área, no uno genérico de "IA". Que una petición
venga de un agente no la exime de los permisos que tendría hecha a mano — si el usuario no
puede editar citas, tampoco puede pedirle a Victor que bloquee una agenda.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlmodel import Session

from api.audit_helper import _audit
from api.auth_deps import CurrentUser, get_current_centro, require_permission
from application.services.agentes_config import estado as estado_agentes, reconciliar, SISTEMA
from application.services.config_service import ConfigService
from application.services.victor_consulta_service import VictorConsultaService
from application.services.victor_service import VictorService
from domain.config.agentes import CATALOGO, POR_ID
from infrastructure.config.db import get_session

router = APIRouter(prefix="/agentes", tags=["ia · agentes"])

VER_PAC = "pacientes.ver"
EDIT_PAC = "pacientes.editar"
VER_CITAS = "citas.ver"
EDIT_CITAS = "citas.editar"
SUPERUSER = "superuser"

# Tamaño máximo del audio de una consulta. 100 MB ≈ 3 h en WAV 16 kHz mono: de sobra para
# una sesión y suficientemente bajo para que nadie tumbe el backend subiendo un vídeo.
MAX_AUDIO = 100 * 1024 * 1024


# ─────────────────────────── CATÁLOGO ───────────────────────────
def _es_superuser(session: Session, user: CurrentUser, centro_id: int) -> bool:
    from application.services.auth_service import AuthService
    return SUPERUSER in AuthService(session).permisos_de(user.usuario_id, centro_id)


@router.get("")
def catalogo(centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission("config.ver")),
             session: Session = Depends(get_session)) -> dict:
    """Quién es quién: parcela, permisos, capacidades y límites de cada agente.

    Lo sirve el catálogo de `domain/config/agentes.py`, que es la fuente única. La pantalla
    NO mantiene su propia copia: si hubiera dos listas, volveríamos al problema de tener
    dos rosters distintos y que nadie supiera cuál manda. Exige config.ver: incluye la ficha
    de Aura (capacidades de administración total), no es algo que vea cualquier empleado."""
    su = _es_superuser(session, user, centro_id)
    return {"agentes": [a.to_dict() for a in CATALOGO if a.id != "aura" or su]}


@router.get("/estado/todos")
def estado_todos(centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("config.ver")),
                 session: Session = Depends(get_session)) -> dict:
    """Estado vivo de cada agente: encendido, operativo (respeta la jerarquía), modelo real
    y capacidades activas. Reconcilia primero para que un agente nuevo del catálogo aparezca."""
    reconciliar(session, centro_id)
    su = _es_superuser(session, user, centro_id)
    return {"agentes": [e for e in estado_agentes(session, centro_id) if e["id"] != "aura" or su]}


@router.get("/permisos/catalogo")
def permisos_catalogo(centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission("config.ver")),
                      session: Session = Depends(get_session)) -> dict:
    """Permisos de la app que se pueden conceder a un agente (combinables). Cada uno abre
    las herramientas que lo exigen (PERMISO_DE_TOOL en agente_service).

    Sale de la MISMA fuente que valida al guardar (`permisos_concedibles`, la tabla
    `permisos`): si la pantalla ofreciera una lista y el guardado validara otra, se podría
    elegir un permiso que luego se rechaza."""
    from application.services.agente_service import permisos_concedibles
    return {"permisos": [{"codigo": c, "descripcion": d}
                         for c, d in sorted(permisos_concedibles(session).items())]}


@router.get("/{agente_id}")
def ficha_agente(agente_id: str,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("config.ver")),
                 session: Session = Depends(get_session)) -> dict:
    if agente_id == "aura" and not _es_superuser(session, user, centro_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Aura solo la ve SuperUser")
    a = POR_ID.get(agente_id)
    return a.to_dict() if a else {"error": f"No existe el agente «{agente_id}»"}


class ToggleIn(BaseModel):
    activa: Optional[bool] = None                 # encender/apagar el agente
    capacidad: Optional[str] = None               # nombre de una capacidad concreta
    valor: Optional[bool] = None                  # su nuevo on/off
    limites_texto: Optional[list[str]] = None     # Límites (Config › Agentes IA)
    permisos_requiere: Optional[list[str]] = None # Permisos de la app concedidos


@router.patch("/{agente_id}/config")
def agente_config(agente_id: str, data: ToggleIn, request: Request,
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission("config.editar")),
                  session: Session = Depends(get_session)) -> dict:
    """Enciende/apaga un agente o una de sus capacidades. Exige config.editar: tocar un
    agente es una decisión de configuración del centro, no de cualquiera que lo mire.

    Aura es SOLO de SuperUser (ver `domain/config/agentes.py`) — que alguien con
    config.editar (cualquier administrador del centro) pudiera encender sus capacidades
    de administración total del sistema rompería esa exclusividad. Se exige `superuser`
    además, solo para este agente."""
    a = POR_ID.get(agente_id)
    if not a:
        return {"ok": False, "motivo": f"No existe el agente «{agente_id}»"}
    if agente_id == "aura":
        from application.services.auth_service import AuthService
        if SUPERUSER not in AuthService(session).permisos_de(user.usuario_id, centro_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo SuperUser puede configurar a Aura")
    cfg = ConfigService(session)
    sistema = SISTEMA.get(a.config_key, "ia")
    actual = cfg.resolve(a.config_key, centro_id=centro_id, sistema=sistema, default={}) or {}
    # Sobre la PLANTILLA, no sobre {}. Un centro que nunca ha pasado por reconciliar no tiene
    # el bloque entero, así que guardar solo `permisos.requiere` dejaba el bloque a medias
    # (sin `auditoria` ni `modo_accion`) y quien lo leyera después se encontraba un KeyError.
    # Lo que ya hubiera elegido el centro sigue mandando: la plantilla solo rellena huecos.
    from application.services.agentes_config import plantilla
    base_def = plantilla(agente_id)
    for bloque in ("capacidades", "permisos", "limites"):
        actual[bloque] = {**base_def.get(bloque, {}), **(actual.get(bloque) or {})}
    actual.setdefault("limites_texto", base_def["limites_texto"])

    if data.activa is not None:
        if agente_id == "gestor":
            # El interruptor de Gestor gobernaba solo un booleano decorativo: lo real es la
            # suscripción push de Gmail (gmail_watch). Antes apagarlo aquí no detenía nada;
            # ahora se pisa contra la API real y solo se persiste si de verdad cambió.
            from infrastructure.external_apis import gmail_watch
            res = (gmail_watch.activar_watch(session, centro_id) if data.activa
                   else gmail_watch.detener_watch(session, centro_id))
            if not res.get("ok"):
                return {"ok": False, "motivo": res.get("error") or "No se pudo cambiar el watch de Gmail"}
        actual["activa"] = data.activa
    if data.capacidad is not None and data.valor is not None:
        if data.capacidad not in a.capacidades:
            return {"ok": False, "motivo": f"«{data.capacidad}» no es una capacidad de {a.nombre}"}
        caps = dict(actual.get("capacidades") or {})
        caps[data.capacidad] = data.valor
        actual["capacidades"] = caps
    if data.limites_texto is not None:
        from application.services.agentes_config import MAX_LIMITE_CHARS, MAX_LIMITES
        limites = [x.strip() for x in data.limites_texto if isinstance(x, str) and x.strip()]
        if len(limites) > MAX_LIMITES:
            return {"ok": False, "motivo": f"Demasiados límites (máximo {MAX_LIMITES})."}
        if any(len(x) > MAX_LIMITE_CHARS for x in limites):
            return {"ok": False, "motivo": f"Cada límite puede tener como mucho {MAX_LIMITE_CHARS} caracteres."}
        actual["limites_texto"] = limites
    if data.permisos_requiere is not None:
        from application.services.agente_service import permisos_concedibles
        validos = permisos_concedibles(session)
        pedidos = list(dict.fromkeys(x.strip() for x in data.permisos_requiere if isinstance(x, str)))
        fuera = sorted(set(pedidos) - set(validos))
        if fuera:
            return {"ok": False, "motivo": f"Permisos que la app no tiene: {fuera}. "
                                           f"Válidos: {', '.join(sorted(validos))}."}
        actual.setdefault("permisos", {})["requiere"] = pedidos
    if all(v is None for v in (data.activa, data.capacidad, data.limites_texto, data.permisos_requiere)):
        return {"ok": False, "motivo": "Nada que cambiar."}

    cfg.set(a.config_key, actual, centro_id=centro_id, sistema=sistema)
    _audit(session, user, centro_id, "agente.config", f"agente:{agente_id}", request,
           {"activa": data.activa, "capacidad": data.capacidad, "valor": data.valor,
            "limites_texto": data.limites_texto, "permisos_requiere": data.permisos_requiere})
    # Devuelve el estado recalculado (para que la UI vea al instante el efecto de la jerarquía).
    return {"ok": True, "estado": next((e for e in estado_agentes(session, centro_id)
                                        if e["id"] == agente_id), None)}


# ─────────────────────────── VICTOR ───────────────────────────
class BloqueoIn(BaseModel):
    doctor: str
    fecha: str                      # AAAA-MM-DD
    desde: Optional[str] = None     # HH:MM (opcional: tramo)
    hasta: Optional[str] = None
    motivo: str = ""
    confirmar: bool = False         # sin esto solo previsualiza


@router.post("/victor/agenda/bloquear")
def victor_bloquear(data: BloqueoIn, request: Request,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission(EDIT_CITAS)),
                    session: Session = Depends(get_session)) -> dict:
    """Bloquea la agenda de un doctor. Sin `confirmar` DEVUELVE LA PREVISUALIZACIÓN.

    La confirmación en dos pasos no es burocracia: un agente entiende mal de vez en cuando,
    y dejar sin agenda a un doctor un día entero por una frase ambigua no se deshace solo."""
    res = VictorService(session, centro_id).bloquear_agenda(
        data.doctor, data.fecha, motivo=data.motivo,
        desde=data.desde, hasta=data.hasta, confirmar=data.confirmar)
    if res.get("confirmado"):
        _audit(session, user, centro_id, "victor.agenda.bloquear", "agenda", request, res)
    return res


@router.delete("/victor/agenda/bloqueo/{bloqueo_id}")
def victor_liberar(bloqueo_id: int, request: Request,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(EDIT_CITAS)),
                   session: Session = Depends(get_session)) -> dict:
    res = VictorService(session, centro_id).liberar_agenda(bloqueo_id)
    _audit(session, user, centro_id, "victor.agenda.liberar", f"bloqueo:{bloqueo_id}", request, res)
    return res


@router.get("/victor/informes/pacientes-sin-venir")
def victor_sin_venir(meses: int = 12, limite: int = 200,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission(VER_PAC)),
                     session: Session = Depends(get_session)) -> dict:
    """Pacientes activos sin visita ATENDIDA desde hace N meses."""
    return VictorService(session, centro_id).pacientes_sin_venir(meses, limite)


@router.get("/victor/resumen-dia")
def victor_resumen(fecha: Optional[str] = None,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(VER_CITAS)),
                   session: Session = Depends(get_session)) -> dict:
    return VictorService(session, centro_id).resumen_dia(fecha)


class VictorChatIn(BaseModel):
    texto: str
    historial: list[dict] = []      # turnos previos, para el "sí, confírmalo"


@router.post("/victor/chat")
def victor_chat(data: VictorChatIn, request: Request,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission(VER_CITAS)),
                session: Session = Depends(get_session)) -> dict:
    """Habla con Victor en lenguaje natural. Él consulta y PREVISUALIZA; nunca ejecuta un
    cambio: las acciones que tocan datos vuelven en `accionesPendientes` para confirmarlas
    con el endpoint /victor/agenda/bloquear (que sí exige permiso de edición)."""
    from application.services.victor_agente import VictorAgente
    return VictorAgente(session, centro_id).responder(data.texto, historial=data.historial)


class GestorChatIn(BaseModel):
    texto: str
    historial: list[dict] = []


@router.post("/gestor/chat")
def gestor_chat(data: GestorChatIn,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("gestoria.ver")),
                session: Session = Depends(get_session)) -> dict:
    """Habla con el Gestor IA en lenguaje natural. Es de SOLO LECTURA: consulta el banco, las
    facturas y los descuadres, pero no cambia nada; los cambios los hace una persona en la
    pantalla de Gestoría (que exige gestoria.editar)."""
    from application.services.gestor_agente import GestorAgente
    return GestorAgente(session, centro_id).responder(data.texto, historial=data.historial)


# ─────────────────────────── VICTOR · CONSULTA ───────────────────────────
@router.get("/victor/consulta/estado")
def victor_consulta_estado(centro_id: int = Depends(get_current_centro),
                           user: CurrentUser = Depends(require_permission(VER_PAC)),
                           session: Session = Depends(get_session)) -> dict:
    """¿Puede Victor escuchar la consulta? Se comprueba contra el proveedor, no contra la
    config.

    Incluye `enviaFuera`: la voz de una consulta es dato de salud y que salga de la clínica
    se dice en pantalla, no se esconde."""
    return VictorConsultaService(session, centro_id).estado()


@router.post("/victor/consulta/escuchar")
async def victor_consulta_escuchar(request: Request,
                        audio: UploadFile = File(...),
                        cita_id: int = Form(...),
                        paciente_id: int = Form(...),
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission(EDIT_PAC)),
                        session: Session = Depends(get_session)) -> dict:
    """Transcribe la consulta y propone el SOAP. Se guarda como BORRADOR.

    Nada de lo que devuelve entra en la historia clínica: el doctor revisa y confirma."""
    datos = await audio.read()
    if len(datos) > MAX_AUDIO:
        return {"ok": False, "motivo": f"El audio supera el máximo ({MAX_AUDIO // (1024*1024)} MB)."}
    if not datos:
        return {"ok": False, "motivo": "El audio llegó vacío."}
    res = VictorConsultaService(session, centro_id).escuchar(
        datos, cita_id=cita_id, paciente_id=paciente_id,
        nombre_archivo=audio.filename or "consulta.wav")
    if res.get("ok"):
        # Se audita el HECHO de escuchar (dato de salud tratado), nunca el contenido.
        _audit(session, user, centro_id, "victor.escuchar_consulta", f"cita:{cita_id}", request,
               {"transcripcionId": res.get("transcripcionId"), "motor": res.get("motor"),
                "duracionSeg": res.get("duracionSeg")})
    return res


# ─────────────────────────── AURA (SuperUser, solo lectura) ───────────────────────────
def _exigir_capacidad(session: Session, centro_id: int, capacidad: str) -> None:
    """Los endpoints REST de Aura pueden llamarse sin pasar por el chat — el interruptor de
    capacidad (Config·Agentes IA·Catálogo) debe cumplirse aquí también, no solo en el LLM."""
    from application.services.agentes_config import capacidad_activa
    if not capacidad_activa(session, centro_id, "aura", capacidad):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Capacidad '{capacidad}' desactivada para Aura")


@router.get("/aura/metricas")
def aura_metricas(centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(SUPERUSER)),
                  session: Session = Depends(get_session)) -> dict:
    _exigir_capacidad(session, centro_id, "consultar_metricas")
    from application.services.aura_service import AuraService
    return AuraService(session, centro_id).metricas()


@router.get("/aura/auditoria")
def aura_auditoria(accion: Optional[str] = None, dias: int = 7,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(SUPERUSER)),
                   session: Session = Depends(get_session)) -> list[dict]:
    _exigir_capacidad(session, centro_id, "consultar_auditoria")
    from application.services.aura_service import AuraService
    return AuraService(session, centro_id).auditoria(accion=accion, dias=dias)


@router.get("/aura/usuarios")
def aura_usuarios(centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(SUPERUSER)),
                  session: Session = Depends(get_session)) -> list[dict]:
    _exigir_capacidad(session, centro_id, "consultar_usuarios")
    from application.services.aura_service import AuraService
    return AuraService(session, centro_id).usuarios_del_centro()


class AuraChatIn(BaseModel):
    texto: str
    historial: list[dict] = []


@router.post("/aura/chat")
def aura_chat(data: AuraChatIn, centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission(SUPERUSER)),
             session: Session = Depends(get_session)) -> dict:
    """Habla con Aura en lenguaje natural.

    Lee métricas, auditoría, usuarios y el estado de Centinela. Desde la v2 también
    administra (usuarios, configuración, agentes), pero nada que escriba se ejecuta sin el
    PIN de SuperUser. El código y la infraestructura siguen siendo cosa de una persona.

    Se le pasa QUIÉN habla: los permisos de la web y el desbloqueo por PIN son de esa
    persona, no del centro. Sin usuario, Aura se queda en solo lectura."""
    from application.services.aura_agente import AuraAgente
    return AuraAgente(session, centro_id, usuario_id=user.usuario_id).responder(
        data.texto, historial=data.historial)


class AuraPinIn(BaseModel):
    pin: str


@router.get("/aura/pin")
def aura_pin_estado(centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission(SUPERUSER)),
                    session: Session = Depends(get_session)) -> dict:
    """¿Hay PIN de escritura fijado? Solo el estado: ni el PIN ni su hash salen jamás."""
    from application.services import aura_pin
    return aura_pin.estado_pin(session, centro_id)


@router.put("/aura/pin")
def aura_pin_fijar(data: AuraPinIn, centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(SUPERUSER)),
                   session: Session = Depends(get_session)) -> dict:
    """Fija o cambia el PIN de escritura de Aura (4–8 dígitos). Cambiarlo cierra al instante
    cualquier sesión desbloqueada. El valor se guarda hasheado y no se audita."""
    from application.services import aura_pin
    r = aura_pin.fijar_pin(session, centro_id, user.usuario_id, data.pin)
    if not r.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, r.get("motivo") or "PIN no válido.")
    return r


@router.get("/aura/centinela")
def aura_centinela(centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(SUPERUSER)),
                   session: Session = Depends(get_session)) -> dict:
    """Espejo en el panel de lo que Aura ve de CENTINELA: nivel actual y avisos recientes.

    Es la misma lectura que hace la herramienta `consultar_centinela` del chat, servida sin
    pasar por el modelo — un panel no necesita que un LLM le resuma su propia bitácora, y
    así el dato no puede salir reescrito.

    Solo LEE auditoría: no lanza revisiones ni remedia nada (eso es `centinela.revisar`, que
    exige PIN). Y respeta el interruptor: si la capacidad está apagada para este centro,
    responde 403 en vez de servir el dato por una puerta distinta a la del chat."""
    from application.services.agentes_config import capacidad_activa
    if not capacidad_activa(session, centro_id, "aura", "consultar_centinela"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "La capacidad «consultar_centinela» está desactivada para Aura "
                            "en este centro.")
    from application.services.aura_admin import _centinela_estado
    return _centinela_estado(session, centro_id, {})
