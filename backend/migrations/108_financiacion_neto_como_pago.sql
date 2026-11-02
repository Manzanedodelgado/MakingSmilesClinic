-- 29-oct-2026: la comisión de la financiera NO es un gasto/Debe: es un no ingreso. En una financiación el
-- paciente paga el 100 % (pagos.importe) y la financiera ingresa menos (pagos.neto); el NETO es lo que cuenta
-- como pago. Se retiran los 85 gastos "Comisión financiera" creados en la 107 (se contarían dos veces) y el
-- informe contable cuenta el neto en los pagos de financiación (si no hay neto, el importe).
DELETE FROM gastos WHERE incidencia = 'comision_financiera' AND numero_factura LIKE 'COM-%'
   AND forma_pago = 'Descuento financiera';

CREATE OR REPLACE VIEW informe_contable AS
SELECT centro_id, 'debe'::text AS seccion,
       EXTRACT(YEAR FROM fecha_operacion)::int AS anyo, EXTRACT(MONTH FROM fecha_operacion)::int AS mes,
       NULL::text AS forma_pago, NULL::text AS estado,
       COUNT(*)::int AS n, ROUND(-SUM(importe), 2) AS importe
  FROM movimientos_bancarios WHERE importe < 0 GROUP BY 1, 3, 4
UNION ALL
SELECT centro_id, 'haber', EXTRACT(YEAR FROM fecha_operacion)::int, EXTRACT(MONTH FROM fecha_operacion)::int,
       NULL, NULL, COUNT(*)::int, ROUND(SUM(importe), 2)
  FROM movimientos_bancarios WHERE importe > 0 GROUP BY 1, 3, 4
UNION ALL
SELECT centro_id, 'facturas', EXTRACT(YEAR FROM fecha)::int, EXTRACT(MONTH FROM fecha)::int,
       COALESCE(NULLIF(forma_pago, ''), '(sin forma de pago)'), estado, COUNT(*)::int, ROUND(SUM(total), 2)
  FROM gastos GROUP BY 1, 3, 4, 5, 6
UNION ALL
SELECT p.centro_id, 'pagos_pacientes', EXTRACT(YEAR FROM p.fecha)::int, EXTRACT(MONTH FROM p.fecha)::int,
       COALESCE(f.grupo, '(sin forma de pago)'), NULL, COUNT(*)::int,
       ROUND(SUM(CASE WHEN f.grupo = 'Financiación' THEN COALESCE(p.neto, p.importe) ELSE p.importe END), 2)
  FROM pagos p LEFT JOIN formas_pago f ON f.id = p.forma_pago_id
 WHERE NOT p.anulado GROUP BY 1, 3, 4, 5;
