-- 29-oct-2026: en las financiaciones el paciente paga el 100 % y la financiera ingresa menos (intereses).
-- Esa diferencia es un GASTO: un gasto "Comisión financiera" por cada transferencia de financiera del Haber,
-- por (pagos de pacientes enlazados al apunte) − (importe ingresado en el banco).
-- No sale del banco: forma de pago 'Descuento financiera' (no bancaria, como el efectivo), sin apunte propio.
INSERT INTO gastos (created_at, updated_at, centro_id, fecha, concepto, base_imponible, iva_pct, total, es_gasto_lab,
                    numero_factura, proveedor_extraido, estado, categoria, incidencia, forma_pago, tipo_documento,
                    fiable, retencion, suplido, seguridad_social, divisa)
SELECT now(), now(), x.centro_id, x.fecha_operacion,
       'Comisión financiera (intereses): los pacientes pagaron ' || to_char(x.bruto, 'FM999G990D00') ||
       ' € y la financiera ingresó ' || to_char(x.banco, 'FM999G990D00') || ' € (apunte ' || x.id || ')',
       round(x.bruto - x.banco, 2), 0, round(x.bruto - x.banco, 2), false,
       'COM-' || x.id,
       CASE WHEN x.concepto_banco ILIKE '%santander%' THEN 'Santander Consumer Finance'
            WHEN x.concepto_banco ILIKE '%pepper%' THEN 'Pepper Finance Corporation'
            WHEN x.concepto_banco ILIKE '%openbank%' THEN 'Openbank'
            ELSE 'Financiera' END,
       'pagada', 'Gastos financieros', 'comision_financiera', 'Descuento financiera', 'otro',
       true, 0, 0, 0, 'EUR'
  FROM (SELECT m.id, m.centro_id, m.fecha_operacion, m.concepto_banco, m.importe AS banco, SUM(p.importe) AS bruto
          FROM movimientos_bancarios m
          JOIN pagos p ON p.liquidacion_mov_id = m.id AND NOT p.anulado
          JOIN formas_pago fp ON fp.id = p.forma_pago_id AND fp.grupo = 'Financiación'
         WHERE m.importe > 0
         GROUP BY m.id, m.centro_id, m.fecha_operacion, m.concepto_banco, m.importe) x
 WHERE x.bruto - x.banco > 0.005
   AND NOT EXISTS (SELECT 1 FROM gastos g WHERE g.numero_factura = 'COM-' || x.id AND g.incidencia = 'comision_financiera');

-- La comisión cuenta como gasto conciliado en el informe del Gestor IA.
CREATE OR REPLACE VIEW informe_gastos AS
SELECT g.centro_id,
       EXTRACT(YEAR FROM COALESCE(m.fecha_operacion, g.fecha))::int AS anyo,
       EXTRACT(MONTH FROM COALESCE(m.fecha_operacion, g.fecha))::int AS mes,
       COALESCE(NULLIF(p.nombre, ''), NULLIF(g.proveedor_extraido, ''), '(sin proveedor)') AS proveedor,
       COALESCE(NULLIF(g.forma_pago, ''), '(sin forma de pago)') AS forma_pago,
       COALESCE(NULLIF(g.categoria, ''), '(sin categoría)') AS categoria,
       COUNT(*)::int AS n, ROUND(SUM(g.total), 2) AS importe
  FROM gastos g
  LEFT JOIN movimientos_bancarios m ON m.id = g.movimiento_id
  LEFT JOIN proveedores p ON p.id = g.proveedor_id
 WHERE g.movimiento_id IS NOT NULL
    OR (g.estado = 'pagada' AND (g.forma_pago = 'Metálico' OR g.forma_pago LIKE 'Tarjeta Deb%' OR g.forma_pago = 'Descuento financiera'))
 GROUP BY 1, 2, 3, 4, 5, 6;
