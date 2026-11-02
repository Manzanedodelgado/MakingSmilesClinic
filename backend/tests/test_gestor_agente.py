"""Gestor IA (chat de Gestoría): una sola herramienta, de solo lectura, sobre el informe contable.

Se prueba el despacho de herramientas directamente (sin LLM): es lo que el modelo usa para no
inventar cifras. Corre sobre SQLite (fixture `session`).
"""
import json
from datetime import date
from decimal import Decimal

from application.services.gestor_agente import GestorAgente, TOOLS
from domain.models.gestoria import Gasto, MovimientoBancario


def _mov(session, importe, f, concepto="TRANSFERENCIA X"):
    m = MovimientoBancario(centro_id=1, iban_cuenta="ES0000000000000000000000", fecha_operacion=f,
                           concepto_banco=concepto, importe=Decimal(str(importe)), estado_concil="abierto")
    session.add(m); session.commit(); session.refresh(m)
    return m


def _fac(session, total, f, mov=None, nf="F1", prov="ACME", forma="Transferencia", estado="pagada"):
    g = Gasto(centro_id=1, fecha=f, total=Decimal(str(total)), numero_factura=nf, proveedor_extraido=prov,
              forma_pago=forma, estado=estado, movimiento_id=mov)
    session.add(g); session.commit(); session.refresh(g)
    return g


def _run(session, nombre, **args):
    return json.loads(GestorAgente(session, 1).ejecutar(nombre, args))


def test_herramientas_son_solo_lectura():
    nombres = {t["function"]["name"] for t in TOOLS}
    assert nombres == {"informe_contable", "informe_gastos", "pagos_juan_antonio"}
    # Ninguna herramienta puede escribir: ni el nombre ni el despacho lo permiten.
    assert not any(p in n for n in nombres for p in ("borrar", "crear", "enlazar", "editar", "actualizar"))
    assert "herramienta desconocida" in GestorAgente.ejecutar(GestorAgente.__new__(GestorAgente), "borrar_factura", {})


def _vista_informe_sqlite(session):
    """En SQLite no hay EXTRACT: se crea un equivalente de la vista `informe_contable` (la real, de
    Postgres, está en la migración 099) para probar el despacho de la herramienta."""
    from sqlalchemy import text
    session.execute(text(
        "CREATE VIEW IF NOT EXISTS informe_contable AS "
        "SELECT centro_id, 'debe' AS seccion, CAST(strftime('%Y', fecha_operacion) AS int) AS anyo, "
        "CAST(strftime('%m', fecha_operacion) AS int) AS mes, NULL AS forma_pago, NULL AS estado, "
        "COUNT(*) AS n, -SUM(importe) AS importe FROM movimientos_bancarios WHERE importe < 0 GROUP BY 1, 3, 4 "
        "UNION ALL SELECT centro_id, 'haber', CAST(strftime('%Y', fecha_operacion) AS int), "
        "CAST(strftime('%m', fecha_operacion) AS int), NULL, NULL, COUNT(*), SUM(importe) "
        "FROM movimientos_bancarios WHERE importe > 0 GROUP BY 1, 3, 4"))
    session.commit()


def test_informe_contable_por_mes_y_seccion(session):
    _vista_informe_sqlite(session)
    _mov(session, -100, date(2025, 3, 1)); _mov(session, -50, date(2025, 3, 2)); _mov(session, 400, date(2025, 4, 3))
    r = _run(session, "informe_contable", anyo=2025)
    assert r["totalesPorSeccion"] == {"debe": 150.0, "haber": 400.0}
    r = _run(session, "informe_contable", seccion="debe", anyo=2025, mes=3)
    assert [(f["mes"], f["n"], f["importe"]) for f in r["filas"]] == [(3, 2, 150.0)]
    assert "error" in _run(session, "informe_contable", mes=13)
    assert "error" in _run(session, "informe_contable", seccion="borrar")
