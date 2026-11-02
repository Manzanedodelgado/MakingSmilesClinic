"""CRM — relación con el paciente. Primer bloque útil: reactivación de inactivos / revisión vencida.

No inventa datos: la 'última actividad' de un paciente es la más reciente entre su último
tratamiento realizado y su último pago. Un paciente es RECUPERABLE si tuvo actividad alguna vez,
sigue activo, y no vuelve desde hace más de `meses`. Es la lista a la que llamar / mandar WhatsApp.
"""
from sqlmodel import Session, text


class CrmService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def inactivos(self, centro_id: int, *, meses: int = 12, limite: int = 500) -> dict:
        """Pacientes activos que NO vuelven desde hace `meses` (pero que sí tuvieron actividad).
        Ordenados por importe histórico gastado (los más valiosos primero)."""
        q = text("""
            WITH act AS (
                SELECT p.id, p.num_historia, p.nombre, p.apellidos,
                       COALESCE(p.telefono_movil, p.telefono_fijo) AS telefono, p.email,
                       GREATEST(
                           COALESCE((SELECT MAX(tr.fecha_inicio) FROM tratamientos_realizados tr
                                     WHERE tr.paciente_id = p.id AND tr.centro_id = :c), DATE '1900-01-01'),
                           COALESCE((SELECT MAX(pg.fecha) FROM pagos pg
                                     WHERE pg.paciente_id = p.id AND pg.anulado = false), DATE '1900-01-01')
                       ) AS ultima_actividad,
                       COALESCE((SELECT SUM(pg.importe) FROM pagos pg
                                 WHERE pg.paciente_id = p.id AND pg.anulado = false), 0) AS gastado
                FROM pacientes p
                WHERE p.centro_id = :c AND p.activo = true
            )
            SELECT id, num_historia, nombre, apellidos, telefono, email, ultima_actividad, gastado,
                   (EXTRACT(YEAR FROM age(CURRENT_DATE, ultima_actividad)) * 12
                    + EXTRACT(MONTH FROM age(CURRENT_DATE, ultima_actividad)))::int AS meses_inactivo
            FROM act
            WHERE ultima_actividad > DATE '1900-01-01'
              AND ultima_actividad < (CURRENT_DATE - (:meses || ' months')::interval)
            ORDER BY gastado DESC, ultima_actividad ASC
            LIMIT :lim
        """)
        rows = self.session.exec(q.bindparams(c=centro_id, meses=meses, lim=limite)).all()
        # Conteo REAL (sin tope) para no engañar cuando la lista se recorta a `limite`.
        total_real = self.session.exec(text("""
            SELECT COUNT(*) FROM pacientes p WHERE p.centro_id = :c AND p.activo = true
              AND GREATEST(
                  COALESCE((SELECT MAX(tr.fecha_inicio) FROM tratamientos_realizados tr
                            WHERE tr.paciente_id = p.id AND tr.centro_id = :c), DATE '1900-01-01'),
                  COALESCE((SELECT MAX(pg.fecha) FROM pagos pg
                            WHERE pg.paciente_id = p.id AND pg.anulado = false), DATE '1900-01-01')
              ) BETWEEN DATE '1900-01-02' AND (CURRENT_DATE - (:meses || ' months')::interval)
        """).bindparams(c=centro_id, meses=meses)).one()
        data = [{
            "id": r[0], "numPac": r[1],
            "paciente": f"{(r[2] or '').strip()} {(r[3] or '').strip()}".strip() or "—",
            "telefono": r[4], "email": r[5],
            "ultimaVisita": str(r[6]) if r[6] else None,
            "gastado": round(float(r[7] or 0), 2),
            "mesesInactivo": int(r[8] or 0),
        } for r in rows]
        return {"meses": meses, "total": int(total_real[0]), "mostrados": len(data), "data": data}

    def pipeline(self, centro_id: int, *, limite: int = 500) -> dict:
        """Embudo de presupuestos: cuánto se presenta vs se cierra, y la lista de presupuestos
        COLGADOS (presentados/nuevos, sin aceptar ni anular) a perseguir — ordenados por importe.
        'Cerrado' = aceptado/en curso/finalizado o con fecha de aceptación; 'perdido' = anulado/cancelado."""
        # 'hecho' = el paciente tuvo pago o tratamiento DESPUÉS del presupuesto → aceptado de facto
        # aunque no esté marcado. Un presupuesto 'colgado' de verdad es el que NO se hizo.
        hecho = ("(EXISTS(SELECT 1 FROM pagos pg WHERE pg.paciente_id=p.paciente_id AND pg.fecha>=p.fecha AND pg.anulado=false)"
                 " OR EXISTS(SELECT 1 FROM tratamientos_realizados tr WHERE tr.paciente_id=p.paciente_id AND tr.fecha_inicio>=p.fecha))")
        colgado = (f"e.codigo IN ('nuevo','entregado') AND p.fecha_aceptacion IS NULL AND NOT {hecho}")
        ganado = (f"(e.codigo IN ('aceptado','en_curso','finalizado','aceptado_parcial') OR p.fecha_aceptacion IS NOT NULL OR {hecho})")
        res = self.session.exec(text(f"""
            SELECT
              COUNT(*) FILTER (WHERE {colgado}) AS pend_n,
              COALESCE(SUM(p.total) FILTER (WHERE {colgado}),0) AS pend_e,
              COUNT(*) FILTER (WHERE {ganado}) AS win_n,
              COALESCE(SUM(p.total) FILTER (WHERE {ganado}),0) AS win_e,
              COUNT(*) FILTER (WHERE e.codigo IN ('anulado','cancelado')) AS lost_n
            FROM presupuestos p LEFT JOIN estados_presupuesto e ON e.id = p.estado_id
            WHERE p.centro_id = :c
        """).bindparams(c=centro_id)).one()
        pend_n, pend_e, win_n, win_e, lost_n = (int(res[0]), float(res[1]), int(res[2]), float(res[3]), int(res[4]))
        conv_n = round(win_n / (win_n + pend_n) * 100, 1) if (win_n + pend_n) else 0.0

        rows = self.session.exec(text("""
            SELECT p.paciente_id, pac.num_historia, pac.nombre, pac.apellidos,
                   COALESCE(pac.telefono_movil, pac.telefono_fijo) AS telefono,
                   p.total, p.fecha, (CURRENT_DATE - p.fecha)::int AS dias
            FROM presupuestos p
            JOIN pacientes pac ON pac.id = p.paciente_id
            LEFT JOIN estados_presupuesto e ON e.id = p.estado_id
            WHERE p.centro_id = :c AND p.total > 0 AND """ + colgado + """
            ORDER BY p.total DESC
            LIMIT :lim
        """).bindparams(c=centro_id, lim=limite)).all()
        colgados = [{
            "pacienteId": r[0], "numPac": r[1],
            "paciente": f"{(r[2] or '').strip()} {(r[3] or '').strip()}".strip() or "—",
            "telefono": r[4], "total": round(float(r[5] or 0), 2),
            "fecha": str(r[6]) if r[6] else None, "dias": int(r[7] or 0),
        } for r in rows]
        return {
            "resumen": {"pendientesN": pend_n, "pendientesEur": round(pend_e, 2),
                        "cerradosN": win_n, "cerradosEur": round(win_e, 2),
                        "perdidosN": lost_n, "conversion": conv_n},
            "mostrados": len(colgados), "colgados": colgados,
        }
