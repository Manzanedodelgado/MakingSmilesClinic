-- 025 · El vínculo factura↔apunte se mueve al lado del GASTO.
--
-- Antes:  movimientos_bancarios.gasto_id  (+ índice ÚNICO parcial uq_mov_gasto)
--         → un apunte apuntaba a UNA factura, y el ÚNICO impedía reutilizar la factura.
--         Físicamente imposible representar un PAGO UNIFICADO (una transferencia que
--         liquida varias facturas del mismo proveedor, p. ej. "Producción Febrero y Marzo").
--
-- Ahora:  gastos.movimiento_id (N facturas → 1 apunte, sin único)
--         Cardinalidad real: una factura se paga con un apunte; un apunte puede pagar varias.
--
-- Se aplica en dos tandas para no tumbar la web en producción:
--   025 (este)  → añade y rellena la columna nueva. NO rompe el código antiguo.
--   026         → borra la columna vieja, ya con el código nuevo desplegado.

BEGIN;

-- Red de seguridad: los 674 enlaces actuales quedan copiados antes de tocar nada.
CREATE TABLE IF NOT EXISTS _snap_mov_gasto_link AS
  SELECT id AS movimiento_id, gasto_id, now() AS copiado_el
  FROM movimientos_bancarios
  WHERE gasto_id IS NOT NULL;

ALTER TABLE gastos ADD COLUMN IF NOT EXISTS movimiento_id INTEGER
  REFERENCES movimientos_bancarios(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_gastos_movimiento_id ON gastos(movimiento_id);

UPDATE gastos g
   SET movimiento_id = m.id
  FROM movimientos_bancarios m
 WHERE m.gasto_id = g.id
   AND g.movimiento_id IS NULL;

COMMIT;
