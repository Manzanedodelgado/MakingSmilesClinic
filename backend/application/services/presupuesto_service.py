"""Creación de presupuestos (capa de aplicación) reutilizable por el router y por las
herramientas del agente Alex. Una sola fuente para el cálculo del total y la numeración
incremental POR PACIENTE. `lineas` son dicts simples:
  {tratamiento_id, pieza?, zona_boca?, colaborador_id?, precio, cantidad?, descuento?, descuento_pct?}
"""
from datetime import date

from sqlalchemy import text
from sqlmodel import Session, select

from domain.models.core import Paciente, Tratamiento
from domain.models.economico import Presupuesto, PresupuestoLinea, TratamientoRealizado

# Estados de presupuesto que NO se tocan (el tratamiento ya no está "disponible"): Anulado, Finalizado, Cancelado.
_ESTADOS_MUERTOS = (2, 5, 7)
from domain.models.economico import (LINEA_ACEPTADA as _LIN_ACEPTADA, LINEA_ANULADA as _LIN_ANULADA,  # noqa: E402
    LINEA_CANCELADA as _LIN_CANCELADA, LINEA_MUERTAS as _LIN_MUERTAS, LINEA_PENDIENTE as _LIN_PENDIENTE,
    LINEA_REALIZADA as _LIN_REALIZADA)
_EST_ACEPTADO = 3
_EST_CANCELADO = 7  # estados_presupuesto: Cancelado (igual que el endpoint /cancelar)
_EST_TTO_PREVISTO = 3  # estados_tratamiento: Previsto (planificado, aún no realizado)


def next_num(session: Session, centro_id: int, paciente_id: int) -> int:
    """Siguiente número de presupuesto del paciente (numeración propia 1,2,3…)."""
    m = session.exec(select(Presupuesto.num_pre).where(
        Presupuesto.centro_id == centro_id,
        Presupuesto.paciente_id == paciente_id,
    ).order_by(Presupuesto.num_pre.desc())).first()
    return (m or 0) + 1


def _total_linea(precio: float, cantidad: int, descuento: float, pct: bool) -> float:
    bruto = precio * (cantidad or 1)
    desc_imp = (bruto * (descuento or 0) / 100.0) if pct else (descuento or 0)
    return max(0.0, bruto - min(desc_imp, bruto))


def _clave(tid: int | None, pieza: str | None, zona: str | None) -> tuple:
    """Identidad clínica de una línea = tratamiento + objetivo (pieza si es de diente; zona_boca si es
    arcada/cuadrante/sextante; nada si es general). Normaliza para comparar."""
    norm = lambda s: "".join(c for c in (s or "") if c.isalnum()).lower()  # noqa: E731
    return (tid, norm(pieza), norm(zona))


def _recalcular_total(session: Session, pre_id: int) -> None:
    lns = session.exec(select(PresupuestoLinea).where(
        PresupuestoLinea.presupuesto_id == pre_id, PresupuestoLinea.estado.notin_(_LIN_MUERTAS))).all()
    tot = sum(_total_linea(float(l.precio_unitario or 0), l.cantidad or 1,
                           float(l.descuento or 0), bool(l.descuento_pct)) for l in lns)
    pre = session.get(Presupuesto, pre_id)
    if pre:
        pre.total = round(tot, 2)
        session.add(pre)


def volcar_a_previstos(session: Session, centro_id: int, paciente_id: int,
                       lineas: list[PresupuestoLinea]) -> int:
    """Aceptar → cada línea aceptada se vuelca a `tratamientos_previstos` (estado 3 = Previsto),
    enlazada por presupuesto_linea_id. Idempotente (borra el previsto anterior de la línea).
    Mensualidad: la línea se DESPLIEGA en N fases (num_tto 1..N, notas "Mensualidad i/N",
    importe = precio unidad). Líneas YA REALIZADAS no se re-planifican.
    Ver docs/PROTOCOLO-PRESUPUESTOS.md."""
    for l in lineas:
        if l.presupuesto.paciente_id != paciente_id or l.presupuesto.centro_id != centro_id:
            raise ValueError("Línea de presupuesto no pertenece al paciente")
    hechas = set(session.exec(select(TratamientoRealizado.presupuesto_linea_id).where(
        TratamientoRealizado.presupuesto_linea_id.in_([l.id for l in lineas]),
        TratamientoRealizado.estado_id == 5)).all()) if lineas else set()
    lineas = [l for l in lineas if l.id not in hechas]
    tids = {l.tratamiento_id for l in lineas if l.tratamiento_id}
    mensualidad: dict[int, bool] = {}
    if tids:
        mensualidad = {t.id: bool(t.es_mensualidad)
                       for t in session.exec(select(Tratamiento).where(Tratamiento.id.in_(tids))).all()}
    ins = text("""
        INSERT INTO tratamientos_previstos
          (created_at, updated_at, centro_id, paciente_id, tratamiento_id, tarifa_precio_id,
           presupuesto_linea_id, colaborador_id, piezas, zona_boca, importe, num_tto, notas, estado_id)
        VALUES (now(), now(), :centro, :pac, :tto, :tp, :lid, :col, :pz, :zb, :imp, :num, :notas, :est)
    """)
    n = 0
    for l in lineas:
        session.connection().execute(
            text("DELETE FROM tratamientos_previstos WHERE presupuesto_linea_id = :lid"), {"lid": l.id})
        precio = float(l.precio_unitario or 0)
        cantidad = l.cantidad or 1
        base = {"centro": centro_id, "pac": paciente_id, "tto": l.tratamiento_id,
                "tp": l.tarifa_precio_id, "lid": l.id, "col": l.colaborador_id,
                "pz": l.pieza, "zb": l.zona_boca, "est": _EST_TTO_PREVISTO}
        if mensualidad.get(l.tratamiento_id):          # N fases, una por mensualidad
            for fase in range(1, cantidad + 1):
                session.connection().execute(ins, {**base, "imp": precio, "num": fase,
                                                   "notas": f"Mensualidad {fase}/{cantidad}"})
                n += 1
        else:                                          # una sola fila
            session.connection().execute(ins, {**base, "imp": precio * cantidad, "num": None, "notas": None})
            n += 1
    return n


def aceptar_entero(session: Session, centro_id: int, paciente_id: int, pre: Presupuesto) -> int:
    """Acepta el presupuesto ENTERO (explícita o implícitamente — p.ej. al realizar en la misma
    cita un tratamiento suyo): todas sus líneas no anuladas → ACEPTADA, cabecera → Aceptado (3)
    con fecha_aceptacion, y TODAS pasan al plan (tratamientos_previstos)."""
    if pre.centro_id != centro_id or pre.paciente_id != paciente_id:
        raise ValueError("Presupuesto no pertenece al paciente")
    lineas = [l for l in session.exec(select(PresupuestoLinea).where(
        PresupuestoLinea.presupuesto_id == pre.id)).all() if l.estado not in _LIN_MUERTAS]
    for l in lineas:
        if l.estado != _LIN_REALIZADA:     # lo ya realizado sigue Realizado
            l.estado = _LIN_ACEPTADA
            session.add(l)
    pre.estado_id = _EST_ACEPTADO
    pre.fecha_aceptacion = date.today()
    session.add(pre)
    n = volcar_a_previstos(session, centro_id, paciente_id, lineas)
    session.commit()
    return n


def anular_tratamientos_en_previos(session: Session, centro_id: int, paciente_id: int,
                                   objetivos: list[tuple], excluir_id: int) -> int:
    """Regla: un tratamiento presupuestado solo está "disponible" mientras su presupuesto esté VIVO
    (no Anulado/Finalizado/Cancelado). Al generar un presupuesto nuevo, si un tratamiento propuesto ya
    existe (mismo tratamiento + pieza + zona) en un presupuesto anterior VIVO, PENDIENTE y NO realizado,
    se CANCELA esa línea allí (ANULADA) y se quita su previsto. `objetivos` = [(tratamiento_id, pieza,
    zona_boca)] del nuevo presupuesto. Devuelve nº de líneas canceladas."""
    claves = {_clave(t, p, z) for (t, p, z) in objetivos if t}
    if not claves:
        return 0
    filas = session.exec(
        select(PresupuestoLinea, Presupuesto)
        .join(Presupuesto, PresupuestoLinea.presupuesto_id == Presupuesto.id)
        .where(Presupuesto.centro_id == centro_id,
               Presupuesto.paciente_id == paciente_id,
               Presupuesto.id != excluir_id,
               Presupuesto.estado_id.notin_(_ESTADOS_MUERTOS),   # type: ignore[union-attr]
               PresupuestoLinea.estado.notin_(_LIN_MUERTAS))).all()
    afectados: set[int] = set()
    n = 0
    for linea, _pre in filas:
        if _clave(linea.tratamiento_id, linea.pieza, linea.zona_boca) not in claves:
            continue
        realizada = session.exec(select(TratamientoRealizado.id).where(
            TratamientoRealizado.presupuesto_linea_id == linea.id,
            TratamientoRealizado.estado_id == 5)).first()
        if realizada:                          # ya realizado → no se cancela
            continue
        # Previsto (aceptado) → Cancelado; Presupuestado (oferta sin aceptar) → Anulado.
        linea.estado = _LIN_CANCELADA if linea.estado == _LIN_ACEPTADA else _LIN_ANULADA
        session.add(linea)
        session.connection().execute(          # quita el previsto proyectado de esa línea (plan coherente)
            text("DELETE FROM tratamientos_previstos WHERE presupuesto_linea_id = :lid"), {"lid": linea.id})
        afectados.add(linea.presupuesto_id)
        n += 1
    for pre_id in afectados:                   # se cancela SOLO la línea (ANULADA); el presupuesto NO se toca
        _recalcular_total(session, pre_id)     # salvo que se quede sin ninguna línea viva → entonces Cancelado (7)
        queda_viva = session.exec(select(PresupuestoLinea.id).where(
            PresupuestoLinea.presupuesto_id == pre_id, PresupuestoLinea.estado.notin_(_LIN_MUERTAS))).first()
        if not queda_viva:
            pre = session.get(Presupuesto, pre_id)
            if pre:
                pre.estado_id = _EST_CANCELADO
                session.add(pre)
    if n:
        session.commit()
    return n


def crear(session: Session, centro_id: int, paciente_id: int, titulo: str | None,
          lineas: list[dict], colaborador_id: int | None = None) -> dict:
    """Crea un presupuesto NUEVO (estado 0) con sus líneas y devuelve {id, num, total}."""
    pac = session.get(Paciente, paciente_id)
    if not pac or pac.centro_id != centro_id:
        raise ValueError("Paciente no encontrado")
    pre = Presupuesto(
        centro_id=centro_id, paciente_id=paciente_id, fecha=date.today(),
        num_pre=next_num(session, centro_id, paciente_id), titulo=titulo,
        colaborador_id=colaborador_id, estado_id=0)
    session.add(pre)
    session.commit()
    session.refresh(pre)
    total = 0.0
    for i, ln in enumerate(lineas, start=1):
        precio = float(ln.get("precio") or 0)
        cant = int(ln.get("cantidad") or 1)
        desc = float(ln.get("descuento") or 0)
        pct = bool(ln.get("descuento_pct"))
        total += _total_linea(precio, cant, desc, pct)
        session.add(PresupuestoLinea(
            presupuesto_id=pre.id, num_linea=i, tratamiento_id=ln.get("tratamiento_id"),
            pieza=ln.get("pieza"), zona_boca=ln.get("zona_boca"),
            colaborador_id=ln.get("colaborador_id"), cantidad=cant, precio_unitario=precio,
            descuento=desc, descuento_pct=pct, estado=_LIN_PENDIENTE))
    pre.total = round(total, 2)
    session.add(pre)
    session.commit()
    # Regla re-presupuestar (misma que el router): lo propuesto cancela su línea repetida
    # pendiente en presupuestos anteriores vivos. Así Alex también respeta el protocolo.
    anuladas = anular_tratamientos_en_previos(
        session, centro_id, paciente_id,
        [(ln.get("tratamiento_id"), ln.get("pieza"), ln.get("zona_boca")) for ln in lineas],
        excluir_id=pre.id)
    return {"id": pre.id, "num": pre.num_pre, "total": pre.total, "anuladas_previas": anuladas}


# ─────────────────────── VALIDEZ de presupuestos aceptados (jmd, 18-oct-2026) ───────────────────────
# Un presupuesto aceptado sin terminar caduca a CANCELADO (7) pasado su plazo desde la aceptación,
# y sus líneas aún Previsto pasan a Cancelado (7); lo realizado se queda Realizado.
#   ortodoncia (alguna línea de mensualidad, o estudio/colocación de ortodoncia realizado) → 24 meses
#   implantes (alguna línea de colocación de implante)                                    →  9 meses
#   resto                                                                                  →  6 meses
_SQL_PLAZO = """
    SELECT p.id,
           CASE WHEN bool_or(t.nombre ~* 'mensualidad'
                             OR (l.estado = 5 AND t.nombre ~* '^(estudio ortodoncia|colocaci.n ortodoncia)')) THEN 24
                WHEN bool_or(t.nombre ~* '^(implante |ocho implantes|siete implantes)') THEN 9
                ELSE 6 END AS meses,
           coalesce(p.fecha_aceptacion, p.fecha) AS fa
      FROM presupuestos p
      JOIN presupuesto_lineas l ON l.presupuesto_id = p.id
      JOIN tratamientos t ON t.id = l.tratamiento_id
     WHERE p.estado_id IN (3, 4, 6)
     GROUP BY p.id"""


def cancelar_fuera_de_plazo(session: Session) -> int:
    """Cancela (7) los presupuestos aceptados/en curso/parciales fuera de plazo con líneas sin
    realizar. Devuelve cuántos presupuestos se cancelaron. Lo llama el job diario."""
    vencidos = [r[0] for r in session.connection().execute(text(f"""
        SELECT x.id FROM ({_SQL_PLAZO}) x
         WHERE x.fa < current_date - make_interval(months => x.meses)
           AND EXISTS (SELECT 1 FROM presupuesto_lineas l WHERE l.presupuesto_id = x.id AND l.estado = :prev)
    """), {"prev": _LIN_ACEPTADA}).all()]
    if not vencidos:
        return 0
    session.connection().execute(text(
        "UPDATE presupuesto_lineas SET estado = :canc, updated_at = now() "
        "WHERE presupuesto_id = ANY(:ids) AND estado = :prev"),
        {"canc": _LIN_CANCELADA, "prev": _LIN_ACEPTADA, "ids": vencidos})
    session.connection().execute(text(
        "DELETE FROM tratamientos_previstos WHERE presupuesto_linea_id IN "
        "(SELECT id FROM presupuesto_lineas WHERE presupuesto_id = ANY(:ids) AND estado = :canc)"),
        {"canc": _LIN_CANCELADA, "ids": vencidos})
    session.connection().execute(text(
        "UPDATE presupuestos SET estado_id = :est, updated_at = now() WHERE id = ANY(:ids)"),
        {"est": _EST_CANCELADO, "ids": vencidos})
    session.commit()
    return len(vencidos)
