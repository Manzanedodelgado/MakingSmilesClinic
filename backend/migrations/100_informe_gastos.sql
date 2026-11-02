-- Informe de gastos del Gestor IA: gastos CONCILIADOS (salen del Debe) por proveedor, año, mes
-- y forma de pago. Conciliado = enlazado a un apunte del banco, o pagado en metálico / con la
-- tarjeta de Juan Antonio (que no pasan por el Debe). Mes = el del apunte del banco si lo hay.
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
    OR (g.estado = 'pagada' AND (g.forma_pago = 'Metálico' OR g.forma_pago LIKE 'Tarjeta Deb%'))
 GROUP BY 1, 2, 3, 4, 5, 6;
