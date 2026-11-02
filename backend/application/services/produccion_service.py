"""GESTORÍA · modo PRODUCCIÓN — liquidación de doctores + facturación de pacientes.

Réplica fiel de la Gestoría .37:
  - Doctores: liquidación con autofactura. Fórmula (accounting.service.ts):
      comisión   = prod_bruta × ratio%        (ratio = colaboradores.pct_produccion)
      gasto_lab  = Σ coste de los trabajos de laboratorio de la tarifa (solo si aplica_laboratorio)
      base_irpf  = comisión − gasto_lab
      irpf       = base_irpf × irpf%           (15% si aplica_irpf)
      a_liquidar = base_irpf − irpf
  - Pacientes: tratamientos no facturados → factura (documentos_admin) + marca num_factura_e.
  - Tratamientos: lista de actos.
Nombre del doctor: colaboradores.periodo_id → usuario_periodos.usuario_id → usuarios.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

# Coste de laboratorio de cada precio de tarifa: Σ cantidad × coste de sus trabajos (migración 076).
_COSTE_LAB_TARIFA = """(
    SELECT tpt.tarifa_precio_id, SUM(tpt.cantidad * lab.coste) AS coste
    FROM tarifa_precio_trabajos tpt JOIN laboratorio_trabajos lab ON lab.id = tpt.laboratorio_trabajo_id
    GROUP BY tpt.tarifa_precio_id)"""

_DOCTOR_JOIN = """
  LEFT JOIN colaboradores   c  ON c.id = tr.colaborador_id
  LEFT JOIN usuario_periodos up ON up.id = c.periodo_id
  LEFT JOIN usuarios        u  ON u.id = up.usuario_id
"""

# Tratamiento marcado "exento de comisión" para ESE doctor (Config→Colaboradores→"Tratamientos
# exentos"): no cuenta a precio real, cuenta al precio único colaboradores.precio_tratamiento_exento
# (0 si no está configurado — "sin comisión" es literal).
_EXENTO_JOIN = """
  LEFT JOIN colaborador_tratamiento_exento cte
    ON cte.colaborador_id = tr.colaborador_id AND cte.tratamiento_id = tr.tratamiento_id
"""
_PROD_LINEA = """
  CASE WHEN cte.tratamiento_id IS NOT NULL THEN COALESCE(c.precio_tratamiento_exento, 0)
       ELSE tr.importe - CASE WHEN tr.descuento_aplica_doctor THEN COALESCE(tr.descuento,0) ELSE 0 END
  END
"""


def _f(v) -> float:
    return round(float(v or 0), 2)


class ProduccionService:
    def __init__(self, session: Session):
        self.session = session

    # ───────────── DOCTORES: liquidación ─────────────
    def doctores(self, centro_id: int, desde: date, hasta: date) -> dict:
        rows = self.session.exec(text(f"""
            SELECT c.id AS col_id,
                   COALESCE(NULLIF(TRIM(COALESCE(u.nombre,'')||' '||COALESCE(u.apellidos,'')),''),'(sin doctor)') AS doctor,
                   u.email AS email,
                   COUNT(*) AS tratamientos,
                   COALESCE(SUM({_PROD_LINEA}),0) AS prod_bruta,
                   COALESCE(MAX(c.pct_produccion),0) AS ratio,
                   COALESCE(bool_or(c.aplica_laboratorio), false) AS aplica_lab,
                   MAX(c.tpc_gastos) AS tpc_gastos,
                   COALESCE(bool_or(c.aplica_irpf), false) AS aplica_irpf,
                   MAX(c.irpf_pct) AS irpf_pct,
                   COALESCE(SUM(lt.coste),0) AS coste_lab
            FROM tratamientos_realizados tr {_DOCTOR_JOIN} {_EXENTO_JOIN}
            LEFT JOIN tarifa_precios tp ON tp.id = tr.tarifa_precio_id
            LEFT JOIN {_COSTE_LAB_TARIFA} lt ON lt.tarifa_precio_id = tp.id
            WHERE tr.centro_id = :c AND tr.fecha_inicio BETWEEN :d AND :h
            GROUP BY c.id, u.nombre, u.apellidos, u.email
            ORDER BY prod_bruta DESC NULLS LAST
        """).bindparams(c=centro_id, d=desde, h=hasta)).all()
        data = [self._liquidar(r) for r in rows]
        return {"periodo": {"desde": str(desde), "hasta": str(hasta)},
                "doctores": len(data),
                "totalTratamientos": sum(d["tratamientos"] for d in data),
                "prodBruta": round(sum(d["prodBruta"] for d in data), 2),
                "prodNeta": round(sum(d["produccionNeta"] for d in data), 2),
                "data": data}

    @staticmethod
    def _liquidar(r) -> dict:
        prod = _f(r.prod_bruta)
        ratio = _f(r.ratio)
        comision = round(prod * ratio / 100, 2)
        # Gastos lab: % configurable (tpc_gastos); fallback 100% si solo está el on/off.
        gastos_pct = _f(r.tpc_gastos) if r.tpc_gastos is not None else (100.0 if r.aplica_lab else 0.0)
        gasto_lab = round(_f(r.coste_lab) * gastos_pct / 100, 2)
        base_irpf = round(comision - gasto_lab, 2)
        # IRPF: % configurable (irpf_pct); fallback 15% si solo está el on/off.
        irpf_pct = _f(r.irpf_pct) if r.irpf_pct is not None else (15.0 if r.aplica_irpf else 0.0)
        deduccion_irpf = round(base_irpf * irpf_pct / 100, 2)
        neta = round(base_irpf - deduccion_irpf, 2)
        return {"doctorId": r.col_id, "doctor": r.doctor, "email": r.email,
                "tratamientos": int(r.tratamientos), "implantes": 0,
                "prodBruta": prod, "acuerdoPct": ratio, "comisionBruta": comision,
                "deduceLaboratorio": bool(r.aplica_lab), "gastosLabReales": gasto_lab,
                "baseIrpf": base_irpf, "irpfPct": irpf_pct, "deduccionIrpf": deduccion_irpf,
                "produccionNeta": neta}

    # ───────────── TRATAMIENTOS: lista de actos ─────────────
    def tratamientos(self, centro_id: int, desde: Optional[date] = None,
                     hasta: Optional[date] = None) -> dict:
        # Rango opcional: sin desde/hasta → todos los años. Sin tope de filas.
        cond = "tr.centro_id = :c"
        params: dict = {"c": centro_id}
        if desde is not None and hasta is not None:
            cond += " AND tr.fecha_inicio BETWEEN :d AND :h"
            params["d"] = desde
            params["h"] = hasta
        rows = self.session.exec(text(f"""
            SELECT tr.id, tr.fecha_inicio, t.nombre AS tratamiento, tr.piezas,
                   COALESCE(NULLIF(TRIM(COALESCE(u.nombre,'')||' '||COALESCE(u.apellidos,'')),''),'—') AS doctor,
                   TRIM(COALESCE(p.nombre,'')||' '||COALESCE(p.apellidos,'')) AS paciente,
                   tr.importe, tr.descuento, tr.descuento_aplica_doctor, tr.num_factura_e,
                   -- Coste de laboratorio: el del propio acto; si no se ha informado, el del
                   -- de los trabajos de laboratorio de su tarifa (de donde bebe la liquidación).
                   COALESCE(tr.coste_laboratorio, lt.coste) AS coste_lab
            FROM tratamientos_realizados tr {_DOCTOR_JOIN}
            LEFT JOIN tratamientos   t  ON t.id = tr.tratamiento_id
            LEFT JOIN pacientes      p  ON p.id = tr.paciente_id
            LEFT JOIN tarifa_precios tp ON tp.id = tr.tarifa_precio_id
            LEFT JOIN {_COSTE_LAB_TARIFA} lt ON lt.tarifa_precio_id = tp.id
            WHERE {cond}
            ORDER BY tr.fecha_inicio DESC NULLS LAST
        """).bindparams(**params)).all()
        cnt = self.session.exec(text(
            f"SELECT COUNT(*) FROM tratamientos_realizados tr WHERE {cond}"
        ).bindparams(**params)).one()
        # Años con datos reales (≥5 actos) para el desplegable — descarta fechas basura sueltas.
        anios = self.session.exec(text(
            "SELECT EXTRACT(YEAR FROM fecha_inicio)::int AS y FROM tratamientos_realizados "
            "WHERE centro_id=:c AND fecha_inicio IS NOT NULL "
            "GROUP BY y HAVING COUNT(*) >= 5 ORDER BY y DESC"
        ).bindparams(c=centro_id)).all()
        data = [{"id": r.id, "fecha": str(r.fecha_inicio) if r.fecha_inicio else None,
                 "tratamiento": r.tratamiento or "—", "piezas": r.piezas, "doctor": r.doctor,
                 "paciente": r.paciente or "—", "importe": _f(r.importe),
                 "descuento": _f(r.descuento), "descuentoAplicaDoctor": bool(r.descuento_aplica_doctor),
                 # null = sin informar (que NO es lo mismo que un coste de 0 €)
                 "costeLaboratorio": None if r.coste_lab is None else _f(r.coste_lab),
                 "facturado": bool(r.num_factura_e)} for r in rows]
        return {"total": int(cnt[0]), "data": data, "anios": [int(r[0]) for r in anios]}

    def actualizar_tratamiento(self, centro_id: int, tto_id: int,
                               descuento: Optional[float] = None,
                               descuento_aplica_doctor: Optional[bool] = None,
                               coste_laboratorio: Optional[float] = None) -> dict:
        """Edita el 'Dto. realizado', si aplica al doctor, y el coste de laboratorio del acto."""
        sets, params = [], {"id": tto_id, "c": centro_id}
        if descuento is not None:
            sets.append("descuento = :desc"); params["desc"] = round(float(descuento), 2)
        if descuento_aplica_doctor is not None:
            sets.append("descuento_aplica_doctor = :ad"); params["ad"] = bool(descuento_aplica_doctor)
        if coste_laboratorio is not None:
            sets.append("coste_laboratorio = :lab"); params["lab"] = round(float(coste_laboratorio), 2)
        if not sets:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nada que actualizar")
        res = self.session.exec(text(
            f"UPDATE tratamientos_realizados SET {', '.join(sets)}, updated_at=now() "
            "WHERE id=:id AND centro_id=:c"
        ).bindparams(**params))
        if res.rowcount != 1:
            self.session.rollback()
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Acto no encontrado")
        self.session.commit()
        r = self.session.exec(text(
            "SELECT descuento, descuento_aplica_doctor, coste_laboratorio "
            "FROM tratamientos_realizados WHERE id=:id"
        ).bindparams(id=tto_id)).first()
        return {"id": tto_id, "descuento": _f(r[0]), "descuentoAplicaDoctor": bool(r[1]),
                "costeLaboratorio": None if r[2] is None else _f(r[2])}

    # ───────────── PACIENTES: tratamientos no facturados + factura ─────────────
    def patient_treatments(self, centro_id: int, paciente_id: int) -> dict:
        pac = self.session.exec(text(
            "SELECT id, TRIM(COALESCE(nombre,'')||' '||COALESCE(apellidos,'')) nom, nif FROM pacientes WHERE id=:p AND centro_id=:c"
        ).bindparams(p=paciente_id, c=centro_id)).first()
        if not pac:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
        rows = self.session.exec(text(f"""
            SELECT tr.id, tr.fecha_inicio, COALESCE(t.nombre, tr.notas) AS concepto,
                   COALESCE(NULLIF(TRIM(COALESCE(u.nombre,'')||' '||COALESCE(u.apellidos,'')),''),'—') AS doctor,
                   tr.importe, tr.descuento, tr.num_factura_e,
                   CASE
                     WHEN d.id IS NOT NULL THEN (d.liquidada OR d.importe_pendiente = 0)
                     ELSE (COALESCE(tr.pendiente, 0) = 0)
                   END AS abonado
            FROM tratamientos_realizados tr {_DOCTOR_JOIN}
            LEFT JOIN tratamientos t ON t.id = tr.tratamiento_id
            LEFT JOIN deudas d ON d.tratamiento_realizado_id = tr.id
            WHERE tr.centro_id=:c AND tr.paciente_id=:p
            ORDER BY tr.fecha_inicio DESC NULLS LAST
        """).bindparams(c=centro_id, p=paciente_id)).all()
        data = []
        for r in rows:
            imp = _f(r.importe)
            desc = _f(r.descuento)
            data.append({"ident": str(r.id), "fecha": str(r.fecha_inicio) if r.fecha_inicio else None,
                         "concepto": r.concepto or "—", "doctor": r.doctor,
                         "importe": imp, "descuento": desc, "neto": round(max(0.0, imp - desc), 2),
                         "facturado": bool(r.num_factura_e), "facturaNumero": r.num_factura_e,
                         "abonado": bool(r.abonado)})
        return {"paciente": {"id": pac.id, "nombre": pac.nom, "nif": pac.nif}, "data": data}

    def create_patient_invoice(self, centro_id: int, paciente_id: int,
                               tto_ids: list[int]) -> dict:
        # Las facturas a pacientes por tratamientos odontológicos están EXENTAS de IVA
        # (asistencia sanitaria, art. 20.Uno.3º Ley 37/1992): no hay desglose de IVA, total = base.
        pac = self.session.exec(text(
            "SELECT id, cliente_id, nombre, apellidos, nif FROM pacientes WHERE id=:p AND centro_id=:c"
        ).bindparams(p=paciente_id, c=centro_id)).first()
        if not pac:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
        if not tto_ids:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selecciona tratamientos")
        hoy = date.today()
        serie = "F"
        nxt = self.session.exec(text(
            "SELECT COALESCE(MAX(num_doc),0)+1 FROM documentos_admin WHERE centro_id=:c AND serie=:s AND anyo=:a"
        ).bindparams(c=centro_id, s=serie, a=hoy.year)).one()
        num = int(nxt[0])
        ids = [int(i) for i in tto_ids]
        concepto = "Tratamientos odontológicos — Exento de IVA (art. 20.Uno.3º Ley 37/1992)"
        factura_id = self.session.exec(text("""
            INSERT INTO documentos_admin (created_at, updated_at, centro_id, cliente_id, tipo_documento,
                   serie, num_doc, anyo, fecha, nombre, apellidos, nif, concepto, abonado, anulada)
            VALUES (now(), now(), :c, :cli, 'factura', :s, :n, :a, :f, :nom, :ape, :nif, :con, false, false)
            RETURNING id
        """).bindparams(c=centro_id, cli=pac.cliente_id, s=serie, n=num, a=hoy.year, f=hoy,
                        nom=pac.nombre, ape=pac.apellidos, nif=pac.nif, con=concepto)).one()[0]
        numero = f"{serie}{num}"
        # Sella el nº de factura SOLO en los tratamientos de ESTE paciente (evita facturar
        # al paciente equivocado si llegan IDs de otro paciente del mismo centro).
        res = self.session.exec(text(
            "UPDATE tratamientos_realizados SET num_factura_e=:nf, factura_documento_id=:fid, updated_at=now() "
            "WHERE centro_id=:c AND paciente_id=:pac AND id = ANY(:ids)"
        ).bindparams(nf=numero, fid=factura_id, c=centro_id, pac=paciente_id, ids=ids))
        if res.rowcount != len(ids):
            self.session.rollback()
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Algún tratamiento no pertenece a este paciente.")
        self.session.commit()
        return {"ok": True, "facturaId": factura_id, "numeroFactura": numero, "serie": serie, "num": num,
                "exento": True, "tratamientos": len(tto_ids)}

    # ───────────── AUTOFACTURA del doctor (liquidación) ─────────────
    def emitir_autofactura(self, centro_id: int, doctor_id: int, desde: date, hasta: date) -> dict:
        rows = self.session.exec(text(f"""
            SELECT c.id col_id, COUNT(*) tt,
                   COALESCE(SUM(tr.importe - CASE WHEN tr.descuento_aplica_doctor
                       THEN COALESCE(tr.descuento,0) ELSE 0 END),0) bruta,
                   COALESCE(MAX(c.pct_produccion),0) ratio,
                   COALESCE(bool_or(c.aplica_laboratorio),false) lab, MAX(c.tpc_gastos) tpc_gastos,
                   COALESCE(bool_or(c.aplica_irpf),false) irpf, MAX(c.irpf_pct) irpf_pct,
                   COALESCE(SUM(lt.coste),0) coste_lab
            FROM tratamientos_realizados tr {_DOCTOR_JOIN}
            LEFT JOIN tarifa_precios tp ON tp.id = tr.tarifa_precio_id
            LEFT JOIN {_COSTE_LAB_TARIFA} lt ON lt.tarifa_precio_id = tp.id
            WHERE tr.centro_id=:c AND tr.colaborador_id=:col AND tr.fecha_inicio BETWEEN :d AND :h
            GROUP BY c.id
        """).bindparams(c=centro_id, col=doctor_id, d=desde, h=hasta)).first()
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor sin producción en el periodo")
        liq = self._liquidar(_FakeRow(rows))
        base = Decimal(str(liq["baseIrpf"]))
        self.session.exec(text("""
            INSERT INTO liquidaciones (created_at, updated_at, centro_id, colaborador_id,
                   periodo_desde, periodo_hasta, base, irpf_pct, liquido, cerrada)
            VALUES (now(), now(), :c, :col, :d, :h, :base, :irpf, :liq, true)
        """).bindparams(c=centro_id, col=doctor_id, d=desde, h=hasta, base=base,
                        irpf=Decimal(str(liq["irpfPct"])), liq=Decimal(str(liq["produccionNeta"]))))
        self.session.commit()
        return {"ok": True, "doctorId": doctor_id, "aLiquidar": liq["produccionNeta"]}


class _FakeRow:
    """Adapta las columnas de emitir_autofactura a los nombres que espera _liquidar."""
    def __init__(self, r):
        self.col_id = r.col_id
        self.doctor = ""
        self.email = None
        self.tratamientos = r.tt
        self.prod_bruta = r.bruta
        self.ratio = r.ratio
        self.aplica_lab = r.lab
        self.tpc_gastos = r.tpc_gastos
        self.aplica_irpf = r.irpf
        self.irpf_pct = r.irpf_pct
        self.coste_lab = r.coste_lab
