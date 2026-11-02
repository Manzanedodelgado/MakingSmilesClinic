-- 064 · Vaciar la tabla pagos (jmd, 17-oct-2026)
-- Orden del usuario: borrar el contenido de la tabla pagos. 14.939 filas, 4.102.290,49 €.
-- Ninguna fila de otra tabla apunta a un pago (comprobado: movimientos_bancarios 0, imputaciones 0).
BEGIN;
DELETE FROM pagos;
DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos;
    IF n > 0 THEN RAISE EXCEPTION '064: quedan % pagos', n; END IF;
END $$;
COMMIT;
