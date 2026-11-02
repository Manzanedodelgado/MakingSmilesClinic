-- 041 · Fase 2 de 040: la forma de pago de los pagos vive SOLO en pagos.forma_pago_id → formas_pago.
-- Se aplica DESPUÉS de desplegar el backend que ya no lee la columna de texto. Idempotente.
-- Se detiene si algún pago con texto quedó sin enlazar (no se pierde información).
BEGIN;
DO $$
DECLARE n integer;
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'pagos' AND column_name = 'forma_pago') THEN
        SELECT count(*) INTO n FROM pagos WHERE forma_pago IS NOT NULL AND forma_pago_id IS NULL;
        IF n > 0 THEN
            RAISE EXCEPTION '041: % pagos con forma de pago en texto sin enlazar a formas_pago', n;
        END IF;
        ALTER TABLE pagos DROP COLUMN forma_pago;
    END IF;
END $$;
COMMIT;
