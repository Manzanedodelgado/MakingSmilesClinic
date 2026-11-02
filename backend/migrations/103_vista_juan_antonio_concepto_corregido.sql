-- Completa la 102: la vista informe_juan_antonio muestra el concepto corregido (si lo hay) sin cambiar el tipo de columna.
-- Detalle línea a línea de Juan Antonio Manzanedo para el Gestor IA (solo lectura, siempre al día).
--   debe    = transferencias del banco a su favor (con la factura enlazada, si es simulación o real)
--   haber   = lo que él ingresa en la cuenta (efectivo o transferencia)
--   tarjeta = gastos a su nombre (internet / IA) pagados con su tarjeta: cuentan como gasto, sin apunte
-- `tipo` solo se asigna con palabras claras del concepto; si no, "Otra transferencia (ver concepto)".
CREATE OR REPLACE VIEW informe_juan_antonio AS
SELECT m.centro_id, 'debe'::text AS origen, m.fecha_operacion AS fecha,
       EXTRACT(YEAR FROM m.fecha_operacion)::int AS anyo, EXTRACT(MONTH FROM m.fecha_operacion)::int AS mes,
       -m.importe AS importe, COALESCE(NULLIF(m.concepto_corregido, ''), m.concepto_banco)::varchar(300) AS concepto, m.id AS apunte_id,
       g.numero_factura AS factura, COALESCE(g.incidencia LIKE 'SIMULACION%', false) AS es_simulacion,
       CASE WHEN m.concepto_banco ~* 'n[oó]mina' THEN 'Pago mensual de su trabajo (nómina / colaboración)'
            WHEN m.concepto_banco ~* 'ortodon' THEN 'Intermediario: ortodoncia'
            ELSE 'Otra transferencia a su favor (ver concepto)' END AS tipo
  FROM movimientos_bancarios m LEFT JOIN gastos g ON g.movimiento_id = m.id
 WHERE m.importe < 0 AND m.concepto_banco ILIKE '%manzanedo%'
UNION ALL
SELECT m.centro_id, 'haber', m.fecha_operacion, EXTRACT(YEAR FROM m.fecha_operacion)::int,
       EXTRACT(MONTH FROM m.fecha_operacion)::int, m.importe, COALESCE(NULLIF(m.concepto_corregido, ''), m.concepto_banco)::varchar(300), m.id, NULL, false,
       CASE WHEN m.concepto_banco ~* 'efectivo' THEN 'Ingreso de efectivo en la cuenta'
            ELSE 'Transferencia recibida de él (ver concepto)' END
  FROM movimientos_bancarios m WHERE m.importe > 0 AND m.concepto_banco ILIKE '%manzanedo%'
UNION ALL
SELECT g.centro_id, 'tarjeta', g.fecha, EXTRACT(YEAR FROM g.fecha)::int, EXTRACT(MONTH FROM g.fecha)::int,
       g.total, g.concepto, NULL, g.numero_factura, false, 'Gasto de internet / IA con su tarjeta'
  FROM gastos g LEFT JOIN proveedores p ON p.id = g.proveedor_id
 WHERE g.movimiento_id IS NULL AND COALESCE(p.nombre, g.proveedor_extraido, '') ILIKE '%manzanedo%';
