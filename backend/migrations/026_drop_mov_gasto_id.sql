-- 026 · Retira la columna vieja del vínculo factura↔apunte.
--
-- Segunda tanda de la migración 025: se ejecuta CON EL CÓDIGO NUEVO YA DESPLEGADO,
-- de modo que en ningún momento hay una versión viva leyendo una columna que no existe.
--
-- El respaldo de los 674 enlaces originales vive en `_snap_mov_gasto_link` (creado en 025).
-- Reversión: recrear la columna y volcar el snapshot.

BEGIN;

-- Nadie debe haber quedado fuera del backfill. Si esto falla, la migración se aborta entera.
DO $$
DECLARE huerfanos INT;
BEGIN
  SELECT COUNT(*) INTO huerfanos
    FROM movimientos_bancarios m
    JOIN gastos g ON g.id = m.gasto_id
   WHERE g.movimiento_id IS DISTINCT FROM m.id;
  IF huerfanos > 0 THEN
    RAISE EXCEPTION 'Migración 026 abortada: % enlaces sin trasladar a gastos.movimiento_id', huerfanos;
  END IF;
END $$;

DROP INDEX IF EXISTS uq_mov_gasto;   -- el ÚNICO que impedía el pago unificado
ALTER TABLE movimientos_bancarios DROP COLUMN IF EXISTS gasto_id;

COMMIT;
