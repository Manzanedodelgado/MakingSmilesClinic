"""Lógica de la tabla nueva `Ttratamientos_pacientes` (unifica presupuestado→previsto→realizado
en UNA fila que solo cambia de estado, en vez de moverse entre presupuesto_lineas /
tratamientos_previstos / tratamientos_realizados). Tabla y catálogo de estados nuevos, sin
SQLModel todavía (como tratamientos_previstos) → SQL crudo. NO toca las tablas existentes:
presupuesto_lineas, tratamientos_previstos y tratamientos_realizados siguen funcionando igual,
esto corre en paralelo mientras se decide la migración.

Máquina de estados (ids de estados_tratamiento):
  1 presupuestado → 3 previsto → 5 realizado
  1 presupuestado → 7 cancelado   (si pasan 3 meses sin aceptar)
  3 previsto      → 6 caducado    (si pasan 3 meses sin realizar)
  3 previsto      → 8 anulado     (si se represupuesta el mismo tratamiento+pieza)
"""
from sqlalchemy import text
from sqlmodel import Session

EST_PREVIO = 2
EST_PRESUPUESTADO = 1
EST_PREVISTO = 3
EST_REALIZADO = 5
EST_CADUCADO = 6
EST_CANCELADO = 7
EST_ANULADO = 8


def _neto(precio, descuento, descuento_pct) -> float:
    precio = float(precio or 0)
    descuento = float(descuento or 0)
    desc = precio * descuento / 100.0 if descuento_pct else descuento
    return round(max(0.0, precio - min(desc, precio)), 2)


def crear_presupuestado(session: Session, *, centro_id: int, paciente_id: int, presupuesto_id: int,
                        tratamiento_id: int | None, pieza_id: int | None, colaborador_id: int | None,
                        precio: float, descuento: float = 0, descuento_pct: bool = False) -> int:
    """Se llama al añadir un tratamiento a un presupuesto: nace la fila en Presupuestado.
    Regla del represupuestado: si el MISMO tratamiento+pieza de ESTE paciente ya estaba en
    Previsto (aceptado, aún no realizado), ese Previsto se anula — el nuevo lo sustituye."""
    total = _neto(precio, descuento, descuento_pct)
    row = session.connection().execute(text("""
        INSERT INTO "Ttratamientos_pacientes"
          (created_at, updated_at, centro_id, paciente_id, estado_id, presupuesto_id,
           tratamiento_id, pieza_id, colaborador_id, precio, descuento, descuento_pct, total)
        VALUES (now(), now(), :centro, :pac, :est, :pre, :tto, :pieza, :col, :precio, :desc, :descpct, :total)
        RETURNING id
    """), {"centro": centro_id, "pac": paciente_id, "est": EST_PRESUPUESTADO, "pre": presupuesto_id,
           "tto": tratamiento_id, "pieza": pieza_id, "col": colaborador_id, "precio": precio,
           "desc": descuento, "descpct": descuento_pct, "total": total}).first()
    nuevo_id = row[0]

    if tratamiento_id and pieza_id:
        session.connection().execute(text("""
            UPDATE "Ttratamientos_pacientes" SET estado_id = :anulado, updated_at = now()
            WHERE paciente_id = :pac AND tratamiento_id = :tto AND pieza_id = :pieza
              AND estado_id = :previsto AND id <> :nuevo
        """), {"anulado": EST_ANULADO, "pac": paciente_id, "tto": tratamiento_id, "pieza": pieza_id,
               "previsto": EST_PREVISTO, "nuevo": nuevo_id})
    return nuevo_id


def aceptar_presupuesto(session: Session, *, presupuesto_id: int) -> int:
    """Al aceptar el presupuesto: todas sus líneas en Presupuestado pasan a Previsto.
    Devuelve cuántas filas cambiaron."""
    res = session.connection().execute(text("""
        UPDATE "Ttratamientos_pacientes" SET estado_id = :previsto, updated_at = now()
        WHERE presupuesto_id = :pre AND estado_id = :presupuestado
    """), {"previsto": EST_PREVISTO, "pre": presupuesto_id, "presupuestado": EST_PRESUPUESTADO})
    return res.rowcount


def realizar(session: Session, *, id_acto: int, notas_doctor: str | None = None) -> bool:
    """Al realizarse: Previsto -> Realizado, guardando la anotación del doctor.
    Solo actúa si el acto estaba en Previsto (no se puede 'realizar' algo cancelado/anulado)."""
    res = session.connection().execute(text("""
        UPDATE "Ttratamientos_pacientes" SET estado_id = :realizado, notas_doctor = :notas, updated_at = now()
        WHERE id = :id AND estado_id = :previsto
    """), {"realizado": EST_REALIZADO, "notas": notas_doctor, "id": id_acto, "previsto": EST_PREVISTO})
    return res.rowcount > 0


def caducar_y_cancelar(session: Session) -> dict:
    """Regla de los 3 meses (job programado, ver infrastructure/scheduler.py):
    Presupuestado sin aceptar en 3 meses -> Cancelado.
    Previsto sin realizar en 3 meses -> Caducado.
    Devuelve cuántas filas cambió cada regla."""
    r1 = session.connection().execute(text("""
        UPDATE "Ttratamientos_pacientes" SET estado_id = :cancelado, updated_at = now()
        WHERE estado_id = :presupuestado AND created_at < now() - interval '3 months'
    """), {"cancelado": EST_CANCELADO, "presupuestado": EST_PRESUPUESTADO})
    r2 = session.connection().execute(text("""
        UPDATE "Ttratamientos_pacientes" SET estado_id = :caducado, updated_at = now()
        WHERE estado_id = :previsto AND updated_at < now() - interval '3 months'
    """), {"caducado": EST_CADUCADO, "previsto": EST_PREVISTO})
    return {"cancelados": r1.rowcount, "caducados": r2.rowcount}


def listar_por_paciente(session: Session, *, paciente_id: int) -> list[dict]:
    rows = session.connection().execute(text("""
        SELECT tp.id, tp.estado_id, et.codigo AS estado, tp.presupuesto_id, tp.tratamiento_id,
               t.nombre AS tratamiento, tp.pieza_id, pz.codigo AS pieza, tp.colaborador_id,
               tp.precio, tp.descuento, tp.descuento_pct, tp.total,
               tp.num_linea_si_realizado, tp.notas_doctor, tp.created_at, tp.updated_at
        FROM "Ttratamientos_pacientes" tp
        JOIN estados_tratamiento et ON et.id = tp.estado_id
        LEFT JOIN tratamientos t ON t.id = tp.tratamiento_id
        LEFT JOIN "Tpiezas" pz ON pz.id = tp.pieza_id
        WHERE tp.paciente_id = :pac
        ORDER BY tp.id
    """), {"pac": paciente_id}).mappings().all()
    return [dict(r) for r in rows]
