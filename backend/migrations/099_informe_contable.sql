-- Informe contable del Gestor IA: UNA vista, siempre al día (se calcula al consultar, no hay
-- nada que refrescar). Solo lee: banco (Debe/Haber), facturas (gastos) y pagos de pacientes.
-- Una fila por centro · sección · año · mes · forma de pago · estado.
--   seccion: debe | haber | facturas | pagos_pacientes
--   importe: Debe en positivo (salidas); Haber y pagos con su signo (devolución = negativo).
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
       COALESCE(f.grupo, '(sin forma de pago)'), NULL, COUNT(*)::int, ROUND(SUM(p.importe), 2)
  FROM pagos p LEFT JOIN formas_pago f ON f.id = p.forma_pago_id
 WHERE NOT p.anulado GROUP BY 1, 3, 4, 5;
