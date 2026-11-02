"""CLÍNICO — recetas emitidas y alta de acto clínico (tratamientos_realizados). Solo BBDD nueva.

Separado de pacientes_router por tamaño (CLAUDE.md: máx 500 líneas/fichero).
Lectura: pacientes.ver · escritura: pacientes.editar (auditada).
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pathlib import Path

from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from domain.models.economico import LINEA_ACEPTADA, LINEA_ACEPTADAS, LINEA_MUERTAS, LINEA_REALIZADA
from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.paciente_helper import _get_paciente
from api.audit_helper import _audit
from application.services.auth_service import AuthService
from application.services.presupuesto_service import aceptar_entero
from application.services.receta_pdf import generar_receta_pdf
from domain.models.agenda import EstadoCita, TipoCita
from domain.models.clinico import AlertaPaciente, MedicPreescrita, PlanProximaCita
from domain.models.core import Centro, Cita, Colaborador, Paciente, Tratamiento
from domain.models.documentos import DocumentoAdmin, DocumentoPaciente, Receta, RecetaLinea, TalonarioReceta
from domain.models.economico import EstadoPresupuesto, Presupuesto, PresupuestoLinea, TratamientoRealizado
from domain.models.identidad import Usuario, UsuarioPeriodo
from infrastructure.config.db import get_session

router = APIRouter(prefix="/pacientes", tags=["pacientes · clínico"])


def _doctores(session: Session) -> dict[int, str]:
    rows = session.exec(
        select(Colaborador.id, Usuario.nombre, Usuario.apellidos)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .join(Usuario, Usuario.id == UsuarioPeriodo.usuario_id)
    ).all()
    return {cid: f"{nom} {ape or ''}".strip() for cid, nom, ape in rows}


# ─────────────────────────── RECETAS EMITIDAS ───────────────────────────
@router.get("/{paciente_id}/recetas")
def recetas(paciente_id: int,
            centro_id: int = Depends(get_current_centro),
            user: CurrentUser = Depends(require_permission("pacientes.ver")),
            session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    recs = session.exec(
        select(Receta).where(Receta.paciente_id == p.id, Receta.anulada == False)  # noqa: E712
        .order_by(Receta.fecha.desc())
    ).all()
    docs = _doctores(session)
    rec_ids = [r.id for r in recs]
    lineas: dict[int, list] = {}
    if rec_ids:
        for ln in session.exec(select(RecetaLinea).where(RecetaLinea.receta_id.in_(rec_ids))).all():
            lineas.setdefault(ln.receta_id, []).append(ln)
    out = []
    for r in recs:
        lns = lineas.get(r.id, [])
        primera = lns[0] if lns else None
        out.append({
            "id": r.id, "fecha": r.fecha.isoformat() if r.fecha else None,
            "medicamento": (primera.farmaco if primera else r.descripcion) or "—",
            "posologia": (primera.posologia if primera else None),
            "pauta": (primera.pauta if primera else None),
            "duracion": (primera.duracion if primera else None),
            "envases": (primera.envases if primera else None),
            "unidades": (primera.unidades if primera else None),
            "doctor": docs.get(r.colaborador_id) or "Inactivo",
            "num_receta": r.cve, "n_lineas": len(lns),
        })
    return {"recetas": out}


@router.get("/{paciente_id}/recetas/{receta_id}/pdf")
def receta_pdf(paciente_id: int, receta_id: int,
               centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("pacientes.ver")),
               session: Session = Depends(get_session)) -> Response:
    """PDF de la receta médica privada (formato oficial), 1 página por medicamento."""
    p = _get_paciente(session, centro_id, paciente_id)
    rec = session.get(Receta, receta_id)
    if not rec or rec.centro_id != centro_id or rec.paciente_id != p.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receta no encontrada")

    # Ya archivada (caso normal desde el fix de guardar_receta): servir el fichero real,
    # no regenerar uno nuevo cada vez que se pide.
    if rec.archivo_url:
        ruta = Path(__file__).resolve().parents[1] / rec.archivo_url.lstrip("/")
        if ruta.exists():
            return FileResponse(str(ruta), media_type="application/pdf",
                                headers={"Content-Disposition": f'inline; filename="receta_{receta_id}.pdf"'})

    lineas = session.exec(select(RecetaLinea).where(RecetaLinea.receta_id == rec.id)
                          .order_by(RecetaLinea.orden_dispensacion)).all()

    numero, cve = "—", rec.cve
    if rec.talonario_receta_id:
        tr = session.get(TalonarioReceta, rec.talonario_receta_id)
        if tr:
            numero, cve = tr.numero, (tr.cve or cve)

    colaborador = session.get(Colaborador, rec.colaborador_id) if rec.colaborador_id else None
    centro = session.get(Centro, centro_id)
    pdf = generar_receta_pdf(
        numero_receta=numero, cve=cve,
        paciente_nombre=f"{p.nombre or ''} {p.apellidos or ''}".strip(),
        paciente_fecha_nac=p.fecha_nacimiento.strftime("%d/%m/%Y") if p.fecha_nacimiento else "",
        paciente_nif=p.nif or "",
        prescriptor_nombre=_doctores(session).get(rec.colaborador_id) or "—",
        num_colegiado=(colaborador.num_colegiado if colaborador else None) or "—",
        centro_direccion=(centro.direccion if centro else "") or "",
        centro_poblacion=(f"{centro.cp or ''} {centro.poblacion or ''}".strip() if centro else ""),
        fecha_prescripcion=rec.fecha, diagnostico=rec.diagnostico or "",
        instrucciones=rec.notas or "", urgencia=rec.urgencia, desabastecimiento=rec.desabastecimiento,
        motivo_sustitucion=rec.notas_farmaceutico or "",
        lineas=[{
            "medicamento": ln.farmaco, "envases": ln.envases, "duracion": ln.duracion,
            "unidades": ln.unidades, "pauta": ln.pauta, "orden": ln.orden_dispensacion,
        } for ln in lineas],
    )
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="receta_{receta_id}.pdf"'})


# ─────────────────────────── ALTA DE ACTO CLÍNICO ───────────────────────────
def _colaborador_de_usuario(session: Session, usuario_id: int) -> Optional[int]:
    """colaborador_id del usuario (vía su periodo) → doctor por defecto de un acto cuando
    no se indica uno explícito. Elige el periodo más reciente si hubiera varios."""
    return session.exec(
        select(Colaborador.id)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .where(UsuarioPeriodo.usuario_id == usuario_id)
        .order_by(UsuarioPeriodo.id.desc())
    ).first()


# Estados de presupuesto que progresan al realizar/borrar actos (ver presupuestos_router).
_EST_ACEPTADO, _EST_EN_CURSO, _EST_FINALIZADO, _EST_PARCIAL = 3, 4, 5, 6


def _recalcular_estado_presupuesto(session: Session, linea_id: Optional[int]) -> None:
    """Deriva el estado del presupuesto de la línea según sus realizados:
    Aceptado/Aceptado parcial → En curso (alguna línea realizada) → Finalizado (todas realizadas).
    Solo afecta a presupuestos en Aceptado/Aceptado parcial/En curso/Finalizado."""
    if not linea_id:
        return
    linea = session.get(PresupuestoLinea, linea_id)
    if not linea:
        return
    if linea.estado in LINEA_ACEPTADAS:
        # Estado de la LÍNEA: Realizado si tiene acto y no le queda ninguna fase en el plan; si no, Previsto.
        hecha = session.exec(select(TratamientoRealizado.id).where(
            TratamientoRealizado.presupuesto_linea_id == linea.id, TratamientoRealizado.estado_id == 5)).first()
        en_plan = session.connection().execute(
            text("SELECT 1 FROM tratamientos_previstos WHERE presupuesto_linea_id = :lid LIMIT 1"),
            {"lid": linea.id}).first()
        nuevo_lin = LINEA_REALIZADA if (hecha and not en_plan) else LINEA_ACEPTADA
        if linea.estado != nuevo_lin:
            linea.estado = nuevo_lin
            session.add(linea); session.commit()
    pre = session.get(Presupuesto, linea.presupuesto_id)
    if not pre or pre.estado_id not in (_EST_ACEPTADO, _EST_PARCIAL, _EST_EN_CURSO, _EST_FINALIZADO):
        return
    lineas = session.exec(select(PresupuestoLinea).where(
        PresupuestoLinea.presupuesto_id == pre.id, PresupuestoLinea.estado.notin_(LINEA_MUERTAS))).all()
    total = len(lineas)
    if total == 0:
        return
    ids = [l.id for l in lineas]
    realizadas = session.exec(select(TratamientoRealizado.presupuesto_linea_id).where(
        TratamientoRealizado.presupuesto_linea_id.in_(ids), TratamientoRealizado.estado_id == 5)).all()
    n = len({r for r in realizadas if r is not None})
    if n == 0:
        # Sin realizados: si estaba En curso/Finalizado (por actos ahora borrados) vuelve a
        # Aceptado; si estaba en Aceptado/Parcial se queda como está.
        if pre.estado_id in (_EST_EN_CURSO, _EST_FINALIZADO):
            pre.estado_id = _EST_ACEPTADO
            session.add(pre); session.commit()
        return
    # Finalizado exige además que no quede NINGUNA fase en el plan (mensualidades: una línea
    # son N previstos; con fases pendientes el presupuesto sigue En curso aunque la línea
    # ya tenga algún acto). Protocolo: docs/PROTOCOLO-PRESUPUESTOS.md.
    pendientes_plan = session.connection().execute(
        text("SELECT 1 FROM tratamientos_previstos WHERE presupuesto_linea_id = ANY(:ids) LIMIT 1"),
        {"ids": ids}).first()
    nuevo = _EST_FINALIZADO if (n >= total and not pendientes_plan) else _EST_EN_CURSO
    if nuevo != pre.estado_id:
        pre.estado_id = nuevo
        session.add(pre); session.commit()


def _restaurar_previsto(session: Session, centro_id: int, paciente_id: int, linea_id: Optional[int]) -> None:
    """Al DESHACER un acto que consumió un previsto, la fase vuelve al PLAN (reversibilidad).
    Mensualidad: deben quedar N − realizados fases; normal: 1 previsto si no queda realizado.
    Ver docs/PROTOCOLO-PRESUPUESTOS.md."""
    if not linea_id:
        return
    linea = session.get(PresupuestoLinea, linea_id)
    if not linea or linea.estado not in LINEA_ACEPTADAS:
        return
    pre = session.get(Presupuesto, linea.presupuesto_id)
    if not pre or pre.estado_id not in (_EST_ACEPTADO, _EST_PARCIAL, _EST_EN_CURSO, _EST_FINALIZADO):
        return
    realizados = len(session.exec(select(TratamientoRealizado.id).where(
        TratamientoRealizado.presupuesto_linea_id == linea_id,
        TratamientoRealizado.estado_id == 5)).all())
    existentes = session.connection().execute(
        text("SELECT count(*) FROM tratamientos_previstos WHERE presupuesto_linea_id = :lid"),
        {"lid": linea_id}).scalar() or 0
    t = session.get(Tratamiento, linea.tratamiento_id) if linea.tratamiento_id else None
    precio = float(linea.precio_unitario or 0)
    if t and t.es_mensualidad:
        n_total = linea.cantidad or 1
        if existentes + realizados >= n_total:
            return
        fase = realizados + 1                     # las fases bajas se consumen primero
        importe, num, notas = precio, fase, f"Mensualidad {fase}/{n_total}"
    else:
        if realizados > 0 or existentes > 0:
            return
        importe, num, notas = precio * (linea.cantidad or 1), None, None
    session.connection().execute(text("""
        INSERT INTO tratamientos_previstos
          (created_at, updated_at, centro_id, paciente_id, tratamiento_id, tarifa_precio_id,
           presupuesto_linea_id, colaborador_id, piezas, zona_boca, importe, num_tto, notas, estado_id)
        VALUES (now(), now(), :centro, :pac, :tto, :tp, :lid, :col, :pz, :zb, :imp, :num, :notas, 3)
    """), {"centro": centro_id, "pac": paciente_id, "tto": linea.tratamiento_id,
           "tp": linea.tarifa_precio_id, "lid": linea_id, "col": linea.colaborador_id,
           "pz": linea.pieza, "zb": linea.zona_boca, "imp": importe, "num": num, "notas": notas})
    session.commit()


class ActoIn(BaseModel):
    tratamiento_id: Optional[int] = None
    piezas: Optional[str] = None          # diente(s) FDI (ámbito 'diente')
    zona_boca: Optional[str] = None       # ámbito amplio: arcada_*/cuadrante_*/sextante_*/boca_completa
    fecha: date
    importe: Optional[float] = None
    notas: Optional[str] = None
    presupuesto_linea_id: Optional[int] = None
    previsto_id: Optional[int] = None     # previsto (plan) que este acto CONSUME → se borra del plan
    colaborador_id: Optional[int] = None


@router.post("/{paciente_id}/actos", status_code=201)
def crear_acto(paciente_id: int, data: ActoIn, request: Request,
               centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("pacientes.editar")),
               session: Session = Depends(get_session)) -> dict:
    """Crea un acto clínico (tratamientos_realizados). Regla dura: aquí NO hay líneas de cobro.
    Regla del centro: NO puede haber un tratamiento realizado SIN doctor → se exige
    colaborador_id (explícito o el del usuario logueado)."""
    p = _get_paciente(session, centro_id, paciente_id)
    if not data.tratamiento_id and not data.notas:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica un tratamiento o una nota")
    colaborador_id = data.colaborador_id or _colaborador_de_usuario(session, user.usuario_id)
    if colaborador_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica el doctor del tratamiento")
    # ACEPTACIÓN IMPLÍCITA (protocolo): realizar un tratamiento de un presupuesto aún NO aceptado
    # (Nuevo/Entregado — p.ej. el generado en esta misma cita) acepta el presupuesto ENTERO →
    # todas sus líneas pasan al plan (previstos); el acto de abajo consumirá el suyo.
    if data.presupuesto_linea_id:
        _lin = session.get(PresupuestoLinea, data.presupuesto_linea_id)
        _pre = session.get(Presupuesto, _lin.presupuesto_id) if _lin else None
        if (
            _pre
            and _pre.centro_id == centro_id
            and _pre.paciente_id == p.id
            and _pre.estado_id in (0, 1)
        ):
            aceptar_entero(session, centro_id, p.id, _pre)
    acto = TratamientoRealizado(
        centro_id=centro_id, paciente_id=p.id, tratamiento_id=data.tratamiento_id,
        piezas=data.piezas, zona_boca=data.zona_boca,
        fecha_inicio=data.fecha, importe=data.importe, notas=data.notas,
        presupuesto_linea_id=data.presupuesto_linea_id, colaborador_id=colaborador_id,
        estado_id=5,  # 5 = Realizado
    )
    session.add(acto); session.commit(); session.refresh(acto)
    aid = acto.id
    # Si el acto consume un previsto (plan), se retira del plan: previsto realizado deja de estar
    # previsto. Sin previsto_id explícito (p.ej. aceptación implícita recién hecha), consume la
    # primera fase pendiente de su línea.
    if data.previsto_id:
        session.connection().execute(
            text("DELETE FROM tratamientos_previstos WHERE id = :i AND paciente_id = :p AND centro_id = :c"),
            {"i": data.previsto_id, "p": p.id, "c": centro_id})
        session.commit()
    elif data.presupuesto_linea_id:
        session.connection().execute(text("""
            DELETE FROM tratamientos_previstos WHERE id = (
              SELECT id FROM tratamientos_previstos WHERE presupuesto_linea_id = :lid
              ORDER BY num_tto NULLS FIRST, id LIMIT 1)"""), {"lid": data.presupuesto_linea_id})
        session.commit()
    # Si el acto viene de una línea de presupuesto, recalcula su estado (En curso / Finalizado).
    _recalcular_estado_presupuesto(session, data.presupuesto_linea_id)
    # Cuenta económica: si el paciente tiene saldo (a cuenta o de este presupuesto), se descuenta.
    from application.services.caja_service import CajaService
    CajaService(session, centro_id).aplicar_saldo(p.id)
    _audit(session, user, centro_id, "actos.crear", f"acto:{aid}", request,
           {"tratamiento_id": data.tratamiento_id, "fecha": data.fecha.isoformat()})
    return {"id": aid}


def _factura_acto_anulada(session: Session, centro_id: int, acto: TratamientoRealizado) -> bool:
    """Solo desbloquea si hay factura anulada y rectificativa archivada enlazada."""
    invoice = None
    if getattr(acto, "factura_documento_id", None):
        invoice = session.exec(select(DocumentoAdmin).where(
            DocumentoAdmin.id == acto.factura_documento_id, DocumentoAdmin.centro_id == centro_id
        )).first()
    elif (acto.num_factura_e or "").strip():
        numero = acto.num_factura_e.strip()
        docs = session.exec(select(DocumentoAdmin).where(
            DocumentoAdmin.centro_id == centro_id, DocumentoAdmin.num_doc.is_not(None)
        )).all()
        matches = [d for d in docs if f"{d.serie or ''}{d.num_doc}" == numero]
        if len(matches) == 1:
            invoice = matches[0]
    if not invoice or not invoice.anulada:
        return False
    rect = session.exec(select(DocumentoPaciente.id).where(
        DocumentoPaciente.paciente_id == acto.paciente_id,
        DocumentoPaciente.factura_origen_id == invoice.id,
        DocumentoPaciente.archivo_url.is_not(None)
    ).limit(1)).first()
    return rect is not None

def _exigir_factura_anulada(session: Session, centro_id: int, acto: TratamientoRealizado) -> None:
    if acto.num_factura_e and not _factura_acto_anulada(session, centro_id, acto):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"El tratamiento está asociado a la factura {acto.num_factura_e}. Anula primero la factura.")


def facturado_al_doctor(f: Optional[date]) -> bool:
    """Regla del centro: el día 10 de cada mes se facturan al doctor los actos del mes
    ANTERIOR. Un acto del mes M queda facturado al llegar el día 10 del mes M+1."""
    if not f:
        return False
    ny, nm = (f.year + 1, 1) if f.month == 12 else (f.year, f.month + 1)
    return date.today() >= date(ny, nm, 10)


def _get_acto(session: Session, centro_id: int, paciente_id: int, acto_id: int) -> TratamientoRealizado:
    a = session.get(TratamientoRealizado, acto_id)
    if not a or a.centro_id != centro_id or a.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Acto no encontrado")
    return a


class ActoEdit(BaseModel):
    tratamiento_id: Optional[int] = None
    piezas: Optional[str] = None
    zona_boca: Optional[str] = None
    fecha: Optional[date] = None
    importe: Optional[float] = None
    notas: Optional[str] = None
    colaborador_id: Optional[int] = None


@router.put("/{paciente_id}/actos/{acto_id}")
def editar_acto(paciente_id: int, acto_id: int, data: ActoEdit, request: Request,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("pacientes.editar")),
                session: Session = Depends(get_session)) -> dict:
    """Edita un acto realizado. El aviso de 'ya facturado al doctor' lo da el frontend
    (la cabecera devuelve `facturado`); aquí se permite y se deja traza en auditoría."""
    p = _get_paciente(session, centro_id, paciente_id)
    a = _get_acto(session, centro_id, p.id, acto_id)
    _exigir_factura_anulada(session, centro_id, a)
    if data.tratamiento_id is not None:
        a.tratamiento_id = data.tratamiento_id
    if data.piezas is not None:
        a.piezas = data.piezas or None
    if data.zona_boca is not None:
        a.zona_boca = data.zona_boca or None
    if data.fecha is not None:
        a.fecha_inicio = data.fecha
    if data.importe is not None:
        a.importe = data.importe
    if data.notas is not None:
        a.notas = data.notas or None
    if data.colaborador_id is not None:
        a.colaborador_id = data.colaborador_id
    session.add(a); session.commit()
    _audit(session, user, centro_id, "actos.editar", f"acto:{acto_id}", request,
           {"facturado": facturado_al_doctor(a.fecha_inicio)})
    return {"id": acto_id}


@router.delete("/{paciente_id}/actos/{acto_id}")
def borrar_acto(paciente_id: int, acto_id: int, request: Request,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("pacientes.editar")),
                session: Session = Depends(get_session)) -> dict:
    """Borra un acto realizado. Si ya está facturado al doctor, el frontend avisa antes."""
    p = _get_paciente(session, centro_id, paciente_id)
    a = _get_acto(session, centro_id, p.id, acto_id)
    _exigir_factura_anulada(session, centro_id, a)
    fact = facturado_al_doctor(a.fecha_inicio)
    linea_id = a.presupuesto_linea_id
    session.delete(a); session.commit()
    # Al deshacer un acto de presupuesto: la fase consumida VUELVE al plan y se recalcula
    # el estado (Finalizado → En curso → Aceptado).
    _restaurar_previsto(session, centro_id, p.id, linea_id)
    _recalcular_estado_presupuesto(session, linea_id)
    _audit(session, user, centro_id, "actos.borrar", f"acto:{acto_id}", request, {"facturado": fact})
    return {"ok": True}



@router.get("/{paciente_id}/alertas")
def alertas(paciente_id: int,
            centro_id: int = Depends(get_current_centro),
            user: CurrentUser = Depends(require_permission("pacientes.ver")),
            session: Session = Depends(get_session)) -> dict:
    """Alertas médicas (alertas_paciente) + medicación habitual (medic_preescrita) + notas. Solo BBDD nueva."""
    p = _get_paciente(session, centro_id, paciente_id)
    al = session.exec(
        select(AlertaPaciente).where(AlertaPaciente.paciente_id == p.id)
        .order_by(AlertaPaciente.activo.desc(), AlertaPaciente.id.desc())
    ).all()
    # Medicación HABITUAL = solo la activa. Las recetas puntuales migradas de GELITE están
    # marcadas inactivas (no son medicación crónica) y no se muestran aquí.
    me = session.exec(
        select(MedicPreescrita).where(MedicPreescrita.paciente_id == p.id, MedicPreescrita.activo == True)  # noqa: E712
        .order_by(MedicPreescrita.fecha_inicio.desc())
    ).all()
    return {
        "alertas": [{
            "id": a.id, "texto": a.texto, "severidad": a.severidad, "activo": a.activo,
            "fecha": a.created_at.isoformat() if a.created_at else None,
        } for a in al],
        "medicaciones": [{
            "id": m.id, "farmaco": m.farmaco, "dosis": m.dosis, "frecuencia": m.frecuencia,
            "pauta": m.pauta, "desde": m.fecha_inicio.isoformat() if m.fecha_inicio else None,
            "activo": m.activo,
        } for m in me],
        "notas": p.notas,
    }


class AlertaIn(BaseModel):
    texto: str
    severidad: Optional[str] = None


@router.post("/{paciente_id}/alertas", status_code=201)
def crear_alerta(paciente_id: int, data: AlertaIn, request: Request,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("pacientes.editar")),
                 session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    if not data.texto.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La alerta no puede estar vacía")
    a = AlertaPaciente(paciente_id=p.id, texto=data.texto.strip(), severidad=data.severidad, activo=True)
    session.add(a); session.commit(); session.refresh(a)
    _audit(session, user, centro_id, "alertas.crear", f"alerta:{a.id}", request, {"paciente_id": p.id})
    return {"id": a.id}


class AlertaUpd(BaseModel):
    activo: Optional[bool] = None
    texto: Optional[str] = None
    severidad: Optional[str] = None


@router.put("/{paciente_id}/alertas/{alerta_id}")
def actualizar_alerta(paciente_id: int, alerta_id: int, data: AlertaUpd, request: Request,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission("pacientes.editar")),
                      session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    a = session.get(AlertaPaciente, alerta_id)
    if not a or a.paciente_id != p.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada")
    if data.activo is not None: a.activo = data.activo
    if data.texto is not None: a.texto = data.texto.strip()
    if data.severidad is not None: a.severidad = data.severidad
    session.add(a); session.commit()
    _audit(session, user, centro_id, "alertas.editar", f"alerta:{a.id}", request, {"activo": a.activo})
    return {"id": a.id, "activo": a.activo}


class MedicIn(BaseModel):
    farmaco: str
    dosis: Optional[str] = None
    frecuencia: Optional[str] = None
    pauta: Optional[str] = None


@router.post("/{paciente_id}/medicaciones", status_code=201)
def crear_medicacion(paciente_id: int, data: MedicIn, request: Request,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission("pacientes.editar")),
                     session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    if not data.farmaco.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica el fármaco")
    m = MedicPreescrita(
        centro_id=centro_id, paciente_id=p.id, farmaco=data.farmaco.strip(),
        dosis=data.dosis, frecuencia=data.frecuencia, pauta=data.pauta,
        fecha_inicio=date.today(), activo=True,
    )
    session.add(m); session.commit(); session.refresh(m)
    _audit(session, user, centro_id, "medicaciones.crear", f"medic:{m.id}", request, {"paciente_id": p.id})
    return {"id": m.id}


# ─────────────────────────── CASCABEL (adherencia) ───────────────────────────
# Estados de cita: 5=finalizada (asistió) · 6=fallada (no-show) · 1/8=anulada/cancelada (excluidas).
_ASISTIDA, _NOSHOW, _CANCELADAS = 5, 6, {1, 8}


@router.get("/{paciente_id}/cascabel")
def cascabel(paciente_id: int,
             centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission("pacientes.ver")),
             session: Session = Depends(get_session)) -> dict:
    """Adherencia del paciente: score de asistencia + historial de citas. Solo BBDD nueva.
    recalls/consents/outcomes van vacíos (sus tablas aún no tienen datos)."""
    p = _get_paciente(session, centro_id, paciente_id)
    today = date.today()
    citas = session.exec(
        select(Cita).where(Cita.paciente_id == p.id).order_by(Cita.fecha.desc(), Cita.hora.desc())
    ).all()
    estados = {e.id: e.nombre for e in session.exec(select(EstadoCita)).all()}
    tipos = {t.id: t.nombre for t in session.exec(select(TipoCita)).all()}

    asistidas = sum(1 for c in citas if c.fecha and c.fecha < today and c.estado_id == _ASISTIDA)
    falladas = sum(1 for c in citas if c.fecha and c.fecha < today and c.estado_id == _NOSHOW)
    total = asistidas + falladas
    score = round(asistidas / total * 100) if total > 0 else None

    timeline = [{
        "id": c.id, "fecha": c.fecha.isoformat() if c.fecha else None, "hora": c.hora,
        "estado": estados.get(c.estado_id) or "—",
        "pasada": bool(c.fecha and c.fecha < today),
        "texto": tipos.get(c.tipo_cita_id) or (c.notas or "")[:60] or None,
    } for c in citas[:15]]

    return {
        "scorePorcentaje": score, "citasAsistidas": asistidas, "citasNoShow": falladas,
        "citasTotal": total, "citas": timeline,
        "recalls": [], "consents": [], "outcomes": [],
    }


# ──────────────────── PLAN PRÓXIMA CITA (doctor → recepción) ────────────────────
def _plan_dict(p: PlanProximaCita) -> dict:
    return {"id": p.id, "minutos": p.minutos, "nota": p.nota, "presupuesto_id": p.presupuesto_id,
            "colaborador_id": p.colaborador_id, "items": p.items or [], "estado": p.estado,
            "fecha": p.created_at.isoformat() if p.created_at else None}


def _plan_pendiente(session: Session, paciente_id: int) -> Optional[PlanProximaCita]:
    return session.exec(
        select(PlanProximaCita).where(PlanProximaCita.paciente_id == paciente_id, PlanProximaCita.estado == "pendiente")
        .order_by(PlanProximaCita.id.desc())
    ).first()


@router.get("/{paciente_id}/plan-proxima")
def get_plan_proxima(paciente_id: int,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission("pacientes.ver")),
                     session: Session = Depends(get_session)) -> dict:
    """Plan pendiente para la próxima cita del paciente (o null). Recepción lo consulta al agendar."""
    p = _get_paciente(session, centro_id, paciente_id)
    plan = _plan_pendiente(session, p.id)
    return {"plan": _plan_dict(plan) if plan else None}


class PlanItemIn(BaseModel):
    linea_id: Optional[int] = None
    tratamiento: str
    pieza: Optional[str] = None
    minutos: int = 0


class PlanIn(BaseModel):
    minutos: int = 0
    nota: Optional[str] = None
    presupuesto_id: Optional[int] = None
    colaborador_id: Optional[int] = None
    items: list[PlanItemIn] = []


@router.put("/{paciente_id}/plan-proxima")
def upsert_plan_proxima(paciente_id: int, data: PlanIn, request: Request,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission("pacientes.editar")),
                        session: Session = Depends(get_session)) -> dict:
    """Crea/actualiza el plan pendiente (uno por paciente)."""
    p = _get_paciente(session, centro_id, paciente_id)
    plan = _plan_pendiente(session, p.id)
    if not plan:
        plan = PlanProximaCita(centro_id=centro_id, paciente_id=p.id, estado="pendiente")
        session.add(plan)
    plan.minutos = max(0, data.minutos)
    plan.nota = data.nota
    plan.presupuesto_id = data.presupuesto_id
    plan.colaborador_id = data.colaborador_id
    plan.items = [i.model_dump() for i in data.items]
    session.commit(); session.refresh(plan)
    _audit(session, user, centro_id, "plan_proxima.guardar", f"plan:{plan.id}", request,
           {"paciente_id": p.id, "items": len(plan.items or []), "minutos": plan.minutos})
    return {"id": plan.id}


@router.delete("/{paciente_id}/plan-proxima", status_code=204)
def delete_plan_proxima(paciente_id: int, request: Request,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission("pacientes.editar")),
                        session: Session = Depends(get_session)) -> None:
    """Cancela el plan pendiente del paciente."""
    p = _get_paciente(session, centro_id, paciente_id)
    plan = _plan_pendiente(session, p.id)
    if plan:
        plan.estado = "cancelada"
        session.add(plan); session.commit()
        _audit(session, user, centro_id, "plan_proxima.cancelar", f"plan:{plan.id}", request, {"paciente_id": p.id})


@router.post("/{paciente_id}/plan-proxima/agendar")
def agendar_plan_proxima(paciente_id: int, request: Request,
                         centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission("pacientes.editar")),
                         session: Session = Depends(get_session)) -> dict:
    """Marca el plan pendiente como 'agendada' (recepción ya dio la cita). Deja de mostrarse."""
    p = _get_paciente(session, centro_id, paciente_id)
    plan = _plan_pendiente(session, p.id)
    if not plan:
        return {"id": None, "estado": None}
    plan.estado = "agendada"
    session.add(plan); session.commit()
    _audit(session, user, centro_id, "plan_proxima.agendar", f"plan:{plan.id}", request, {"paciente_id": p.id})
    return {"id": plan.id, "estado": "agendada"}
