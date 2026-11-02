-- 043 · Los cobros de la aplicación anterior son pagos Eurodent (jmd, 17-oct-2026)
-- La 042 metió los 991 movimientos negativos de TtosMed (2001-2019) en `pagos` con dos formas
-- INVENTADAS (17 y 18), que no existen en el catálogo de Gesden (TForPago 1-15).
-- Criterio del usuario: los pagos en negativo de GELITE hasta el 31-12-2019 incluido son Eurodent;
-- a partir de esa fecha un negativo puede ser una devolución. Los 991 son todos <= 2019-12-31.
-- No se tocan los pagos negativos que YA traen forma real de PagoCli.IdForPago. Idempotente.
BEGIN;

UPDATE pagos SET forma_pago_id = 14, updated_at = now()
 WHERE forma_pago_id IN (17, 18)
   AND fecha <= DATE '2019-12-31';

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos WHERE forma_pago_id IN (17, 18);
    IF n > 0 THEN RAISE EXCEPTION '043: quedan % pagos con las formas inventadas 17/18', n; END IF;
END $$;

DELETE FROM formas_pago WHERE id IN (17, 18);

COMMIT;
