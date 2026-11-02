-- Extractos bancarios: la unicidad de un apunte debe incluir el SALDO POSTERIOR.
--
-- Problema: `uq_mov_banc` era UNIQUE (iban, fecha, concepto, importe). Dos movimientos
-- REALES idénticos del mismo día (mismo concepto y mismo importe — p.ej. dos
-- transferencias de producción al mismo colaborador el mismo día) chocaban contra la
-- restricción y el segundo NUNCA llegaba a guardarse: se perdía el apunte y su dinero
-- desaparecía de los libros. Confirmado en datos reales (22/01/2026, dos transferencias
-- de 1.200,00 € el mismo día; solo constaba una).
--
-- Arreglo: incluir `saldo_posterior` en la clave. Es un saldo CORRIDO, luego es distinto
-- en cada apunte aunque el resto coincida: distingue dos movimientos reales de una
-- re-importación del mismo extracto (que sí trae saldos idénticos y se sigue omitiendo).
--
-- NOTA: en Postgres, NULL nunca es igual a NULL en un UNIQUE, así que los extractos sin
-- columna de saldo dejan de tener protección a nivel de BD; para esos, la deduplicación
-- por multiplicidad vive en `GestoriaService.import_movimientos`.

ALTER TABLE movimientos_bancarios DROP CONSTRAINT IF EXISTS uq_mov_banc;

ALTER TABLE movimientos_bancarios
  ADD CONSTRAINT uq_mov_banc UNIQUE (iban_cuenta, fecha_operacion, concepto_banco, importe, saldo_posterior);
