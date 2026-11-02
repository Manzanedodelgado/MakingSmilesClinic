-- 071 · Pagos desde el 3-09-2019 con Talón, Domiciliación o Pago Eurodent → Efectivo (jmd, 17-oct-2026)
-- Orden del usuario. Talón (5) y Domiciliación (2) ya se pasaron a Efectivo en la 068; queda 1 Eurodent.
BEGIN;
UPDATE pagos SET forma_pago_id = 2, updated_at = now()
 WHERE fecha >= DATE '2019-09-03' AND forma_pago_id IN (1, 5, 14);
DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos WHERE fecha >= DATE '2019-09-03' AND forma_pago_id IN (1, 5, 14);
    IF n > 0 THEN RAISE EXCEPTION '071: quedan %', n; END IF;
END $$;
COMMIT;
