"""Configuración · PERSONAL y COLABORADORES — sobre el modelo de periodos.

personal → `usuarios` (identidad, global) + `usuario_periodos` (cada etapa alta/baja,
con `centro_id` propio — migración 020) + rol/login vía `user_center_roles` (opcional,
no todo el staff tiene login). colaboradores → `colaboradores` (económico de UNA etapa,
colgando de `periodo_id`) + `colaborador_centro` (N:M, un doctor puede trabajar en varios
centros). Identidad única en `usuarios`; la pertenencia a un centro es de la ETAPA/del
colaborador, no de la persona. Cero duplicación, cero base64 (firma = URL). Toda
escritura se audita.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, get_current_user, require_permission
from api.audit_helper import _audit
from application.services.auth_service import AuthService, PERMISO_NO_GESTIONABLE
from domain.models.core import (
    Colaborador, ColaboradorCentro, Tratamiento, ColaboradorTratamientoExento, ColaboradorTipoCita,
)
from domain.models.agenda import TipoCita, Gabinete, ColaboradorHorario
from domain.models.identidad import (
    Permiso, Rol, RolePermiso, Usuario, UserCenterPermiso, UserCenterPermisoDenegado, UserCenterRole, UsuarioPeriodo,
)
from infrastructure.config.db import get_session
from infrastructure.security import hash_password

router = APIRouter(prefix="/configuracion", tags=["configuración · personal & colaboradores"])


def _catalogo_permisos(session: Session) -> list[Permiso]:
    """Permisos asignables como 'áreas' en Personal (todos menos superuser), orden estable."""
    rows = session.exec(select(Permiso).where(Permiso.codigo.notin_(PERMISO_NO_GESTIONABLE)).order_by(Permiso.id)).all()
    return list(rows)


# Presentación: agrupa los pares `<area>.ver` / `<area>.editar` en ÁREAS legibles con nivel.
# El catálogo de permisos es la fuente de verdad; esto solo lo ordena para marcarlo por área.
_AREAS_PERMISOS = [
    ("pacientes", "Pacientes"),
    ("citas", "Agenda"),
    ("comunicacion", "Comunicación / WhatsApp"),
    ("informes", "Informes"),
    ("gestoria", "Gestoría"),
    ("config", "Configuración"),
]


# Pestañas por área (código = `<area>.tab.<id>`). Una pestaña solo cuenta si hay también `<area>.ver`.
_TABS_AREA = {
    "pacientes": [("ficha", "Ficha"), ("filiacion", "Filiación"), ("presupuestos", "Presupuestos"),
                  ("documentos", "Documentos"), ("plan-econ", "Plan económico")],
    "gestoria": [("facturacion", "Facturación"), ("produccion", "Producción")],
    "config": [("clinica", "Clínica"), ("admin", "Admin"), ("conectores", "Conectores"),
               ("automatizaciones", "Automatizaciones"), ("flujos", "Flujos"), ("agentes", "Agentes IA")],
}
# Secciones dentro de una pestaña (código = `<area>.tab.<pestaña>.<sección>`).
_SUBS_TAB = {
    "facturacion": [('debehaber', 'Debe / Haber'), ('facturas', 'Facturas'), ('pagos', 'Pagos'), ('impuestos', 'Impuestos'), ('envio', 'Envío'), ('historico', 'Histórico'), ('gestor', 'Gestor IA')],
    "produccion": [('tratamientos', 'Tratamientos'), ('doctores', 'Doctores'), ('pacientes', 'Pacientes')],
    "clinica": [('centro', 'Centro'), ('agenda', 'Agenda'), ('personal', 'Personal'), ('colaboradores', 'Colaboradores')],
    "admin": [('diseno', 'Diseño'), ('documentos', 'Documentos'), ('tablas', 'Tablas')],
    "conectores": [('whatsapp', 'WhatsApp'), ('voicebot', 'Voicebot'), ('mail', 'Mail'), ('drive', 'Drive'), ('radiografias', 'Radiografías'), ('servidor', 'Servidor')],
    "automatizaciones": [('reglas', 'Reglas'), ('editor', 'Editor'), ('plantillas', 'Plantillas')],
    "flujos": [('flujos', 'Flujos'), ('editor', 'Editor')],
}


def _areas_estructuradas(session: Session) -> tuple[list[dict], list[dict]]:
    """(áreas, extras). Cada área = {key, nombre, ver?, editar?}. Los permisos del catálogo
    que no encajan en el patrón ver/editar de un área (p.ej. gestoria.facturacion.ver, el
    acceso restringido de asesoría) se devuelven como `extras` = toggles sueltos."""
    cat = {p.codigo: (p.descripcion or p.codigo) for p in _catalogo_permisos(session)}
    usados: set[str] = set()
    areas: list[dict] = []
    for key, nombre in _AREAS_PERMISOS:
        ver, editar = f"{key}.ver", f"{key}.editar"
        entry: dict = {"key": key, "nombre": nombre}
        if ver in cat:
            entry["ver"] = ver; usados.add(ver)
        if editar in cat:
            entry["editar"] = editar; usados.add(editar)
        tabs = []
        for t, n in _TABS_AREA.get(key, []):
            cod = f"{key}.tab.{t}"
            if cod not in cat:
                continue
            subs = [{"codigo": f"{cod}.{x}", "nombre": xn} for x, xn in _SUBS_TAB.get(t, []) if f"{cod}.{x}" in cat]
            tabs.append({"codigo": cod, "nombre": n, **({"subs": subs} if subs else {})})
            usados.add(cod); usados.update(x["codigo"] for x in subs)
        if tabs:
            entry["tabs"] = tabs
        if "ver" in entry or "editar" in entry:
            areas.append(entry)
    extras = [{"codigo": c, "nombre": d} for c, d in cat.items() if c not in usados]
    return areas, extras


def _permisos_de_usuario(session: Session, usuario_id: int, centro_id: int) -> list[str]:
    """Permisos EFECTIVOS de la persona en el centro: (rol − denegados) ∪ directos."""
    return sorted(AuthService(session).permisos_de(usuario_id, centro_id))


def _permisos_directos(session: Session, usuario_id: int, centro_id: int) -> list[str]:
    """Concesiones directas heredadas (user_center_permisos), fuera de lo que da el rol."""
    return sorted(session.exec(
        select(Permiso.codigo)
        .join(UserCenterPermiso, UserCenterPermiso.permiso_id == Permiso.id)
        .where(UserCenterPermiso.usuario_id == usuario_id, UserCenterPermiso.centro_id == centro_id)
    ).all())


def _permisos_de_rol(session: Session, usuario_id: int, centro_id: int) -> set[str]:
    """Permisos gestionables que concede el rol de la persona en el centro."""
    return set(session.exec(
        select(Permiso.codigo)
        .join(RolePermiso, RolePermiso.permiso_id == Permiso.id)
        .join(UserCenterRole, UserCenterRole.rol_id == RolePermiso.rol_id)
        .where(UserCenterRole.usuario_id == usuario_id, UserCenterRole.centro_id == centro_id)
    ).all()) - PERMISO_NO_GESTIONABLE


def _sync_permisos(session: Session, usuario_id: int, centro_id: int, codigos: Optional[list[str]]) -> None:
    """Fija los permisos EFECTIVOS de la persona (WYSIWYG sobre lo marcado en Personal).

    El rol es el techo: lo que el rol da y no viene marcado se guarda como DENEGADO de esa
    persona (límite); nunca se concede por encima del rol. Sin rol con permisos (R vacío) rige
    el modo anterior: lo marcado se concede como permiso directo. Los directos heredados que
    sigan marcados se conservan. Solo toca el catálogo gestionable (superuser intacto).
    Si `codigos` es None (no vino en el body) no cambia nada."""
    if codigos is None:
        return
    catalogo = {p.codigo: p.id for p in _catalogo_permisos(session)}
    deseados = {c for c in codigos if c in catalogo}            # ignora códigos desconocidos
    rol = _permisos_de_rol(session, usuario_id, centro_id) & set(catalogo)
    directos_act = set(_permisos_directos(session, usuario_id, centro_id)) & set(catalogo)
    if rol:
        excedidos = deseados - rol - directos_act
        if excedidos:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "El rol no incluye: " + ", ".join(sorted(excedidos)) +
                                ". Amplía el rol en Config › Clínica › Centro › Roles.")
        directos_obj = (deseados - rol) & directos_act
    else:
        directos_obj = deseados
    denegados_obj = rol - deseados
    ids = set(catalogo.values())
    # directos: dejar exactamente directos_obj (dentro del catálogo)
    for a in session.exec(select(UserCenterPermiso).where(
            UserCenterPermiso.usuario_id == usuario_id, UserCenterPermiso.centro_id == centro_id)).all():
        if a.permiso_id in ids and a.permiso_id not in {catalogo[c] for c in directos_obj}:
            session.delete(a)
    for c in directos_obj - directos_act:
        session.add(UserCenterPermiso(usuario_id=usuario_id, centro_id=centro_id, permiso_id=catalogo[c]))
    # denegados: dejar exactamente denegados_obj
    actuales_den = session.exec(select(UserCenterPermisoDenegado).where(
        UserCenterPermisoDenegado.usuario_id == usuario_id, UserCenterPermisoDenegado.centro_id == centro_id)).all()
    obj_den_ids = {catalogo[c] for c in denegados_obj}
    for d in actuales_den:
        if d.permiso_id in ids and d.permiso_id not in obj_den_ids:
            session.delete(d)
    ya = {d.permiso_id for d in actuales_den}
    for pid in obj_den_ids - ya:
        session.add(UserCenterPermisoDenegado(usuario_id=usuario_id, centro_id=centro_id, permiso_id=pid))


# Identidad de la PERSONA (tabla usuarios)
USUARIO_IDENTIDAD = {"nombre", "apellidos", "nif", "email", "username", "telefono", "color"}
# Lo que es de la ETAPA (tabla usuario_periodos)
PERIODO_EDITABLE = {"staff_tipo", "tipo_contrato", "fecha_alta", "fecha_baja"}
# Económico/profesional de la etapa (tabla colaboradores)
COLAB_EDITABLE = {
    "num_colegiado", "firma_url",
    "contrato_inicio", "contrato_fin", "factura_produccion", "pct_produccion",
    "aplica_laboratorio", "tpc_gastos", "aplica_irpf", "irpf_pct",
    "ausencia_inicio", "ausencia_fin", "activo",
    "precio_tratamiento_exento",
}


def _es_activo(p: Optional[UsuarioPeriodo]) -> bool:
    """Activo = hay un periodo abierto (sin fecha de baja cumplida)."""
    return p is not None and (p.fecha_baja is None or p.fecha_baja > date.today())


def _periodo_vigente(session: Session, usuario_id: int) -> Optional[UsuarioPeriodo]:
    """El periodo abierto; si no hay ninguno, la última etapa (mayor orden)."""
    periodos = session.exec(
        select(UsuarioPeriodo).where(UsuarioPeriodo.usuario_id == usuario_id)
        .order_by(UsuarioPeriodo.orden.desc())
    ).all()
    if not periodos:
        return None
    abierto = next((p for p in periodos if p.fecha_baja is None or p.fecha_baja > date.today()), None)
    return abierto or periodos[0]


def _codigo_periodo(usuario_id: int, orden: int) -> str:
    """Código visible: idUsuario para la 1ª etapa, idUsuario.n para reactivaciones."""
    return str(usuario_id) if orden == 0 else f"{usuario_id}.{orden}"


def _colab_de_periodo(session: Session, periodo_id: Optional[int]) -> Optional[Colaborador]:
    if not periodo_id:
        return None
    return session.exec(select(Colaborador).where(Colaborador.periodo_id == periodo_id)).first()


def _usuario_en_centro(session: Session, usuario_id: int, centro_id: int) -> bool:
    """C5 (migración 020): pertenece a ESTE centro si tiene alguna etapa laboral ahí."""
    return session.exec(
        select(UsuarioPeriodo.id)
        .where(UsuarioPeriodo.usuario_id == usuario_id, UsuarioPeriodo.centro_id == centro_id)
    ).first() is not None


def _get_usuario_del_centro(session: Session, usuario_id: int, centro_id: int) -> Usuario:
    """404 (no 403) si el usuario no pertenece al centro — no revela si el ID existe en otro centro."""
    if not _usuario_en_centro(session, usuario_id, centro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    u = session.get(Usuario, usuario_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return u


def _colaborador_en_centro(session: Session, colaborador_id: int, centro_id: int) -> bool:
    """C5: `colaborador_centro` (N:M, ya existía para "un doctor trabaja en varios centros")."""
    return session.exec(
        select(ColaboradorCentro.centro_id)
        .where(ColaboradorCentro.colaborador_id == colaborador_id, ColaboradorCentro.centro_id == centro_id)
    ).first() is not None


def _get_colaborador_del_centro(session: Session, colaborador_id: int, centro_id: int) -> Colaborador:
    if not _colaborador_en_centro(session, colaborador_id, centro_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colaborador no encontrado")
    col = session.get(Colaborador, colaborador_id)
    if not col:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colaborador no encontrado")
    return col


# ─────────────────────────── PERSONAL (usuarios + periodo vigente) ───────────────────────────
class UsuarioIn(BaseModel):
    nombre: str
    apellidos: Optional[str] = None
    nif: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    telefono: Optional[str] = None
    color: Optional[str] = None
    # de la etapa vigente
    staff_tipo: Optional[str] = None
    tipo_contrato: Optional[str] = None
    fecha_alta: Optional[date] = None
    fecha_baja: Optional[date] = None   # vacía = etapa abierta = activo
    rol_id: Optional[int] = None
    password: Optional[str] = None   # si viene, se (re)establece el hash
    permisos: Optional[list[str]] = None   # áreas habilitadas (códigos de permiso); None = no tocar


def _periodo_entry(session: Session, usuario_id: int, p: UsuarioPeriodo) -> dict:
    col = _colab_de_periodo(session, p.id)
    return {
        "id": p.id, "orden": p.orden, "codigo": _codigo_periodo(usuario_id, p.orden),
        "staff_tipo": p.staff_tipo, "tipo_contrato": p.tipo_contrato,
        "fecha_alta": p.fecha_alta, "fecha_baja": p.fecha_baja, "abierto": _es_activo(p),
        "colaborador_id": col.id if col else None,
    }


def _usuario_dto(session: Session, u: Usuario, centro_id: int) -> dict:
    ucr = session.exec(
        select(UserCenterRole).where(UserCenterRole.usuario_id == u.id, UserCenterRole.centro_id == centro_id)
    ).first()
    rol = session.get(Rol, ucr.rol_id) if ucr else None
    periodos = session.exec(
        select(UsuarioPeriodo).where(UsuarioPeriodo.usuario_id == u.id).order_by(UsuarioPeriodo.orden)
    ).all()
    p = _periodo_vigente(session, u.id)
    col = _colab_de_periodo(session, p.id) if p else None
    return {
        "id": u.id, "nombre": u.nombre, "apellidos": u.apellidos, "nif": u.nif, "email": u.email,
        "username": u.username, "telefono": u.telefono, "color": u.color,
        # de la etapa vigente (mismo contrato que esperaba el front)
        "staff_tipo": p.staff_tipo if p else None, "tipo_contrato": p.tipo_contrato if p else None,
        "fecha_alta": p.fecha_alta if p else None, "fecha_baja": p.fecha_baja if p else None,
        "periodo_id": p.id if p else None, "periodo_codigo": _codigo_periodo(u.id, p.orden) if p else None,
        "activo": _es_activo(p),
        "periodos": [_periodo_entry(session, u.id, x) for x in periodos],  # historial de etapas
        "tiene_login": bool(u.password_hash), "rol_id": ucr.rol_id if ucr else None,
        "rol_nombre": rol.nombre if rol else None,
        "colaborador_id": col.id if col else None,
        "permisos": _permisos_de_usuario(session, u.id, centro_id),  # efectivos: (rol − límites) ∪ directos
        "permisos_rol": sorted(_permisos_de_rol(session, u.id, centro_id)),   # techo que da su rol
        "permisos_directos": _permisos_directos(session, u.id, centro_id),    # heredados, fuera del rol
    }


@router.get("/personal")
def list_personal(centro_id: int = Depends(get_current_centro), _u: CurrentUser = Depends(get_current_user),
                  session: Session = Depends(get_session)) -> dict:
    # Personal = TODA la gente que trabaja o ha trabajado EN ESTE CENTRO (alguna etapa
    # en usuario_periodos con este centro_id — migración 020). El login, el rol/acceso
    # y el ser colaborador son atributos opcionales, no requisitos.
    usuarios = session.exec(
        select(Usuario)
        .join(UsuarioPeriodo, UsuarioPeriodo.usuario_id == Usuario.id)
        .where(UsuarioPeriodo.centro_id == centro_id)
        .order_by(Usuario.nombre)
        .distinct()
    ).all()
    roles = session.exec(select(Rol).where(Rol.centro_id == centro_id).order_by(Rol.nombre)).all()
    areas, extras = _areas_estructuradas(session)
    return {"personal": [_usuario_dto(session, u, centro_id) for u in usuarios],
            "roles": [{"id": r.id, "nombre": r.nombre,
                       "permisos": sorted(c for c in session.exec(
                           select(Permiso.codigo).join(RolePermiso, RolePermiso.permiso_id == Permiso.id)
                           .where(RolePermiso.rol_id == r.id)).all() if c not in PERMISO_NO_GESTIONABLE)}
                      for r in roles],
            # Permisos agrupados en ÁREAS con nivel Ver/Editar (marcación legible en Personal).
            "permiso_areas": areas, "permiso_extras": extras}


def _apply_rol(session: Session, usuario_id: int, centro_id: int, rol_id: Optional[int]) -> None:
    if rol_id is None:
        return
    ucr = session.exec(
        select(UserCenterRole).where(UserCenterRole.usuario_id == usuario_id, UserCenterRole.centro_id == centro_id)
    ).first()
    if ucr:
        ucr.rol_id = rol_id
    else:
        ucr = UserCenterRole(usuario_id=usuario_id, centro_id=centro_id, rol_id=rol_id)
    session.add(ucr)


@router.post("/personal", status_code=201)
def create_personal(data: UsuarioIn, request: Request, centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("config.editar")),
                    session: Session = Depends(get_session)) -> dict:
    # Alta: crea identidad nueva y la ata a ESTE centro vía UserCenterRole — no hay
    # usuario_id externo que un caller pueda desviar a otro centro, sin bug de pertenencia.
    u = Usuario(
        nombre=data.nombre, apellidos=data.apellidos, nif=data.nif, email=data.email,
        username=data.username, telefono=data.telefono, color=data.color,
        password_hash=hash_password(data.password) if data.password else None,
    )
    session.add(u); session.commit(); session.refresh(u)
    session.add(UsuarioPeriodo(
        usuario_id=u.id, centro_id=centro_id, orden=0, staff_tipo=data.staff_tipo, tipo_contrato=data.tipo_contrato,
        fecha_alta=data.fecha_alta, fecha_baja=data.fecha_baja,
    ))
    rol_id = data.rol_id or _rol_por_defecto(session, centro_id)
    _apply_rol(session, u.id, centro_id, rol_id)
    _sync_permisos(session, u.id, centro_id, data.permisos)   # áreas marcadas → user_center_permisos
    session.commit()
    _audit(session, user, centro_id, "config.personal.crear", f"usuario:{u.id}", request)
    return _usuario_dto(session, session.get(Usuario, u.id), centro_id)


@router.put("/personal/{usuario_id}")
def update_personal(usuario_id: int, data: UsuarioIn, request: Request, centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("config.editar")),
                    session: Session = Depends(get_session)) -> dict:
    u = _get_usuario_del_centro(session, usuario_id, centro_id)
    cambios = data.model_dump(exclude_unset=True)
    for k, v in cambios.items():
        if k in USUARIO_IDENTIDAD:
            setattr(u, k, v)
    if data.password:
        u.password_hash = hash_password(data.password)
    session.add(u)
    # la etapa vigente recibe staff_tipo/contrato/fechas
    p = _periodo_vigente(session, usuario_id)
    if p is None:
        p = UsuarioPeriodo(usuario_id=usuario_id, centro_id=centro_id, orden=0)
    for k, v in cambios.items():
        if k in PERIODO_EDITABLE:
            setattr(p, k, v)
    session.add(p)
    _apply_rol(session, u.id, centro_id, data.rol_id)
    _sync_permisos(session, usuario_id, centro_id, data.permisos)   # áreas marcadas → user_center_permisos
    session.commit()
    _audit(session, user, centro_id, "config.personal.editar", f"usuario:{usuario_id}", request,
           {k: v for k, v in cambios.items() if k != "password"})
    return _usuario_dto(session, session.get(Usuario, usuario_id), centro_id)


class ColabToggle(BaseModel):
    colaborador: bool


@router.put("/personal/{usuario_id}/colaborador")
def set_personal_colaborador(usuario_id: int, data: ColabToggle, request: Request,
                             centro_id: int = Depends(get_current_centro),
                             user: CurrentUser = Depends(require_permission("config.editar")),
                             session: Session = Depends(get_session)) -> dict:
    """On-off de colaborador sobre la ETAPA vigente de la persona.

    ON  → crea el `colaboradores` colgando del periodo vigente. Requiere persona activa
          (lógicamente, un inactivo no puede ser colaborador).
    OFF → quita el colaborador del periodo. Se borra si no tiene historial; si lo tiene,
          se conserva desvinculado (periodo_id = NULL) para no perder citas/liquidaciones.
    """
    u = _get_usuario_del_centro(session, usuario_id, centro_id)
    p = _periodo_vigente(session, usuario_id)
    col = _colab_de_periodo(session, p.id) if p else None

    if data.colaborador:
        if not _es_activo(p):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Una persona inactiva no puede ser colaborador")
        if not col:
            nuevo = Colaborador(periodo_id=p.id, activo=True)
            session.add(nuevo); session.commit()
            session.add(ColaboradorCentro(colaborador_id=nuevo.id, centro_id=centro_id)); session.commit()
            _audit(session, user, centro_id, "config.personal.colaborador.on", f"usuario:{usuario_id}",
                   request, {"colaborador_id": nuevo.id, "periodo_id": p.id})
    else:
        if col:
            col_id = col.id
            try:
                session.execute(sa_delete(ColaboradorCentro).where(ColaboradorCentro.colaborador_id == col_id))
                session.execute(sa_delete(Colaborador).where(Colaborador.id == col_id))
                session.commit()
            except IntegrityError:
                session.rollback()  # tiene historial → se conserva desvinculado
                col2 = session.get(Colaborador, col_id)
                if col2:
                    col2.periodo_id = None
                    session.add(col2); session.commit()
            _audit(session, user, centro_id, "config.personal.colaborador.off", f"usuario:{usuario_id}",
                   request, {"colaborador_id": col_id})

    return _usuario_dto(session, session.get(Usuario, usuario_id), centro_id)


class ReactivarIn(BaseModel):
    modo: str                              # "mismos" | "diferentes"
    fecha_alta: Optional[date] = None
    staff_tipo: Optional[str] = None       # solo modo "diferentes"
    tipo_contrato: Optional[str] = None    # solo modo "diferentes"


@router.post("/personal/{usuario_id}/reactivar")
def reactivar_personal(usuario_id: int, data: ReactivarIn, request: Request,
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("config.editar")),
                       session: Session = Depends(get_session)) -> dict:
    """Abre una nueva etapa (periodo) para una persona inactiva.

    ① "mismos"     → copia staff_tipo/contrato del último periodo y, si era colaborador,
                     replica su económico en la nueva etapa. Solo cambia la fecha de alta.
    ② "diferentes" → etapa nueva con los datos indicados (staff_tipo/contrato), sin colaborador.
    """
    u = _get_usuario_del_centro(session, usuario_id, centro_id)
    periodos = session.exec(
        select(UsuarioPeriodo).where(UsuarioPeriodo.usuario_id == usuario_id).order_by(UsuarioPeriodo.orden)
    ).all()
    vigente = _periodo_vigente(session, usuario_id)
    if _es_activo(vigente):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La persona ya está activa")

    nuevo_orden = (max((p.orden for p in periodos), default=-1)) + 1
    if data.modo == "mismos" and vigente is not None:
        np = UsuarioPeriodo(usuario_id=usuario_id, centro_id=centro_id, orden=nuevo_orden, staff_tipo=vigente.staff_tipo,
                            tipo_contrato=vigente.tipo_contrato, fecha_alta=data.fecha_alta, fecha_baja=None)
        session.add(np); session.flush()
        prev = _colab_de_periodo(session, vigente.id)
        if prev:   # replica el económico de colaborador en la nueva etapa
            session.add(Colaborador(
                periodo_id=np.id, num_colegiado=prev.num_colegiado, firma_url=prev.firma_url,
                factura_produccion=prev.factura_produccion, pct_produccion=prev.pct_produccion,
                aplica_laboratorio=prev.aplica_laboratorio, aplica_irpf=prev.aplica_irpf,
                precio_tratamiento_exento=prev.precio_tratamiento_exento, activo=True,
            ))
    else:
        np = UsuarioPeriodo(usuario_id=usuario_id, centro_id=centro_id, orden=nuevo_orden, staff_tipo=data.staff_tipo,
                            tipo_contrato=data.tipo_contrato, fecha_alta=data.fecha_alta, fecha_baja=None)
        session.add(np)
    session.commit()
    _audit(session, user, centro_id, "config.personal.reactivar", f"usuario:{usuario_id}",
           request, {"modo": data.modo, "orden": nuevo_orden})
    return _usuario_dto(session, session.get(Usuario, usuario_id), centro_id)


def _rol_por_defecto(session: Session, centro_id: int) -> Optional[int]:
    r = session.exec(select(Rol).where(Rol.centro_id == centro_id).order_by(Rol.id)).first()
    return r.id if r else None


# ─────────────────────────── COLABORADORES ───────────────────────────
# Solo económico/profesional de una etapa. Identidad y contrato vienen del usuario/periodo.
class DuracionTipoCitaIn(BaseModel):
    tipo_cita_id: int
    duracion_min: int


class ColaboradorIn(BaseModel):
    num_colegiado: Optional[str] = None
    firma_url: Optional[str] = None
    contrato_inicio: Optional[date] = None
    contrato_fin: Optional[date] = None
    factura_produccion: bool = False
    pct_produccion: Optional[float] = None
    aplica_laboratorio: bool = False
    tpc_gastos: Optional[float] = None        # % gastos de laboratorio (lo consume produccion_service)
    aplica_irpf: bool = False
    irpf_pct: Optional[float] = None          # % IRPF de la liquidación (produccion/conciliacion)
    ausencia_inicio: Optional[date] = None
    ausencia_fin: Optional[date] = None
    tratamientos_exentos: Optional[list[int]] = None          # varios tratamientos exentos de comisión
    precio_tratamiento_exento: Optional[float] = None         # precio único de la exención
    duraciones: Optional[list[DuracionTipoCitaIn]] = None     # duración (min) por tipo de cita
    activo: bool = True


def _colaborador_dto(session: Session, col: Colaborador, p: Optional[UsuarioPeriodo], u: Optional[Usuario]) -> dict:
    """Económico del colaborador + identidad del usuario + contrato del periodo (fuente única)."""
    exentos = session.exec(select(ColaboradorTratamientoExento.tratamiento_id)
                           .where(ColaboradorTratamientoExento.colaborador_id == col.id)).all()
    durs = session.exec(select(ColaboradorTipoCita)
                        .where(ColaboradorTipoCita.colaborador_id == col.id)).all()
    hors = session.exec(select(ColaboradorHorario)
                        .where(ColaboradorHorario.colaborador_id == col.id)
                        .order_by(ColaboradorHorario.dia_semana, ColaboradorHorario.hora_inicio)).all()
    return {
        "id": col.id, "usuario_id": u.id if u else None,
        "periodo_id": col.periodo_id,
        "periodo_codigo": _codigo_periodo(u.id, p.orden) if (u and p) else None,
        "nombre": u.nombre if u else None, "apellidos": u.apellidos if u else None,
        "color": u.color if u else None, "nif": u.nif if u else None,
        "tipo_contrato": p.tipo_contrato if p else None,
        "num_colegiado": col.num_colegiado, "firma_url": col.firma_url,
        "contrato_inicio": col.contrato_inicio, "contrato_fin": col.contrato_fin,
        "factura_produccion": col.factura_produccion, "pct_produccion": col.pct_produccion,
        "aplica_laboratorio": col.aplica_laboratorio, "tpc_gastos": col.tpc_gastos,
        "aplica_irpf": col.aplica_irpf, "irpf_pct": col.irpf_pct,
        "ausencia_inicio": col.ausencia_inicio, "ausencia_fin": col.ausencia_fin,
        "tratamientos_exentos": list(exentos),
        "precio_tratamiento_exento": col.precio_tratamiento_exento,
        "duraciones": [{"tipo_cita_id": d.tipo_cita_id, "duracion_min": d.duracion_min} for d in durs],
        "horarios": [{"id": h.id, "dia_semana": h.dia_semana, "hora_inicio": h.hora_inicio,
                      "hora_fin": h.hora_fin, "pausa_inicio": h.pausa_inicio, "pausa_fin": h.pausa_fin,
                      "gabinete_id": h.gabinete_id} for h in hors],
        "activo": col.activo,
    }


def _periodo_usuario_de_colaborador(session: Session, col: Colaborador):
    p = session.get(UsuarioPeriodo, col.periodo_id) if col.periodo_id else None
    u = session.get(Usuario, p.usuario_id) if p else None
    return p, u


@router.get("/colaboradores")
def list_colaboradores(centro_id: int = Depends(get_current_centro), _u: CurrentUser = Depends(get_current_user),
                       session: Session = Depends(get_session)) -> dict:
    # C5: acotado vía `colaborador_centro` (N:M ya existente — "un doctor trabaja en varios centros").
    rows = session.exec(
        select(Colaborador, UsuarioPeriodo, Usuario)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .join(Usuario, Usuario.id == UsuarioPeriodo.usuario_id)
        .join(ColaboradorCentro, ColaboradorCentro.colaborador_id == Colaborador.id)
        .where(ColaboradorCentro.centro_id == centro_id)
        .order_by(Usuario.nombre)
        .distinct()
    ).all()
    return {"colaboradores": [_colaborador_dto(session, c, p, u) for c, p, u in rows]}


@router.get("/tratamientos")
def list_tratamientos(centro_id: int = Depends(get_current_centro), _u: CurrentUser = Depends(get_current_user),
                      session: Session = Depends(get_session)) -> dict:
    """Catálogo ligero (id · código · nombre) para selectores — p.ej. tratamiento exento."""
    rows = session.exec(
        select(Tratamiento).where(Tratamiento.centro_id == centro_id).order_by(Tratamiento.nombre)
    ).all()
    return {"tratamientos": [{"id": t.id, "codigo": t.codigo, "nombre": t.nombre} for t in rows]}


@router.get("/tipos-cita")
def list_tipos_cita(centro_id: int = Depends(get_current_centro), _u: CurrentUser = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> dict:
    """Catálogo ligero (id · nombre · color) de tipos de cita — para tiempos por colaborador."""
    rows = session.exec(
        select(TipoCita).where(TipoCita.centro_id == centro_id, TipoCita.activo == True).order_by(TipoCita.nombre)  # noqa: E712
    ).all()
    return {"tipos_cita": [{"id": t.id, "nombre": t.nombre, "color": t.color} for t in rows]}


@router.get("/gabinetes")
def list_gabinetes(centro_id: int = Depends(get_current_centro), _u: CurrentUser = Depends(get_current_user),
                   session: Session = Depends(get_session)) -> dict:
    """Catálogo ligero (id · nombre) de gabinetes — para el horario del colaborador."""
    rows = session.exec(
        select(Gabinete).where(Gabinete.centro_id == centro_id, Gabinete.activo == True).order_by(Gabinete.nombre)  # noqa: E712
    ).all()
    return {"gabinetes": [{"id": g.id, "nombre": g.nombre} for g in rows]}


# No hay alta suelta de colaborador: se crea marcando a una persona en Personal
# (PUT /personal/{id}/colaborador). Aquí solo se edita su económico.
@router.put("/colaboradores/{colaborador_id}")
def update_colaborador(colaborador_id: int, data: ColaboradorIn, request: Request,
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("config.editar")),
                       session: Session = Depends(get_session)) -> dict:
    col = _get_colaborador_del_centro(session, colaborador_id, centro_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        if k in COLAB_EDITABLE:
            setattr(col, k, v)
    # Contrato vencido → inactivo (regla del usuario: al cumplirse 'contrato hasta' se marca
    # inactivo, sin borrar NADA anterior). Solo fuerza la baja; la reactivación es manual
    # (casilla Activo) tras renovar/ampliar la fecha — un contrato en curso no se auto-fuerza.
    if col.contrato_fin and col.contrato_fin < date.today():
        col.activo = False
    # exentos (N:M) — reemplazo completo si la lista viene
    if data.tratamientos_exentos is not None:
        session.execute(sa_delete(ColaboradorTratamientoExento)
                        .where(ColaboradorTratamientoExento.colaborador_id == col.id))
        for tid in dict.fromkeys(data.tratamientos_exentos):  # dedupe preservando orden
            session.add(ColaboradorTratamientoExento(colaborador_id=col.id, tratamiento_id=tid))
    # duraciones por tipo de cita — reemplazo completo si la lista viene (solo minutos > 0)
    if data.duraciones is not None:
        session.execute(sa_delete(ColaboradorTipoCita)
                        .where(ColaboradorTipoCita.colaborador_id == col.id))
        seen: set[int] = set()
        for d in data.duraciones:
            if d.tipo_cita_id in seen or d.duracion_min is None or d.duracion_min <= 0:
                continue
            seen.add(d.tipo_cita_id)
            session.add(ColaboradorTipoCita(colaborador_id=col.id, tipo_cita_id=d.tipo_cita_id, duracion_min=d.duracion_min))
    session.add(col); session.commit()
    _audit(session, user, centro_id, "config.colaborador.editar", f"colaborador:{colaborador_id}", request)
    col = session.get(Colaborador, colaborador_id)
    p, u = _periodo_usuario_de_colaborador(session, col)
    return _colaborador_dto(session, col, p, u)


@router.post("/colaboradores/{colaborador_id}/talonario/importar", status_code=201)
async def importar_talonario(colaborador_id: int, request: Request,
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("config.editar")),
                       session: Session = Depends(get_session)) -> dict:
    """Importar números de talonario oficial (CSV, XML, XLSX) asignado a un colaborador."""
    from domain.models.documentos import Talonario, TalonarioReceta
    import xml.etree.ElementTree as ET

    col = _get_colaborador_del_centro(session, colaborador_id, centro_id)

    # Parsear FormData
    form_data = await request.form()
    archivo = form_data.get('archivo')
    numero_lote = form_data.get('numero_lote', '').strip()

    if not archivo or not numero_lote:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "archivo y numero_lote requeridos")

    # Leer contenido del archivo
    contenido = await archivo.read()
    texto = contenido.decode('utf-8', errors='ignore')

    numeros: list[str] = []
    cves: list[str] = []

    # Parsear según tipo de archivo
    if archivo.filename.endswith('.xml'):
        try:
            root = ET.fromstring(contenido)
            # Buscar en elementos: <receta>, <numero>, o cualquier elemento con atributos numero/cve
            for elem in root.iter():
                num = elem.get('numero') or elem.find('numero')
                cve = elem.get('cve') or elem.find('cve')

                if num is not None:
                    num_str = num if isinstance(num, str) else (num.text or "")
                    cve_str = cve if isinstance(cve, str) else (cve.text or "" if cve is not None else "")

                    if num_str.strip():
                        numeros.append(num_str.strip())
                        cves.append(cve_str.strip())
        except ET.ParseError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "XML inválido")

    elif archivo.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Excel no soportado aún. Usa CSV o XML")

    else:  # CSV / TXT
        lineas = texto.strip().split('\n')
        for linea in lineas:
            if not linea.strip():
                continue
            partes = [p.strip() for p in linea.split(',')]
            if partes and partes[0]:
                numeros.append(partes[0])
                cves.append(partes[1] if len(partes) > 1 else "")

    if not numeros:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No se encontraron números en el archivo")

    # Crear talonario
    tal = Talonario(
        centro_id=centro_id,
        colaborador_id=colaborador_id,
        numero_lote=numero_lote,
        total_numeros=len(numeros),
        activo=True,
    )
    session.add(tal)
    session.flush()

    # Crear números
    for i, num in enumerate(numeros):
        cve = cves[i] if i < len(cves) else ""
        tr = TalonarioReceta(
            talonario_id=tal.id,
            numero=num,
            cve=cve if cve else None,
            usada=False,
        )
        session.add(tr)

    # Vincular talonario al colaborador
    col.talonario_id = tal.id
    session.add(col)
    session.commit()

    _audit(session, user, centro_id, "config.talonario.importar", f"colaborador:{colaborador_id}:talonario:{tal.id}", request)

    return {
        "ok": True,
        "talonario_id": tal.id,
        "numero_lote": tal.numero_lote,
        "numeros_importados": len(numeros),
    }
