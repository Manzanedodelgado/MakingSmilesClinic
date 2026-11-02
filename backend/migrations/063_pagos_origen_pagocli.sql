-- 063 · Marcar la procedencia de los pagos migrados de GELITE (jmd, 17-oct-2026)
-- Los 13.948 pagos sin `origen` son exactamente los de GELITE PagoCli (13.948 / 3.871.814,64 €
-- en las dos bases, verificado). Se marcan como tales.
-- Motivo además de la norma de procedencia: la cuenta económica de la app solo puede gastar
-- dinero NACIDO EN LA APP. Estos pagos ya pagaron sus tratamientos en GELITE y esa imputación
-- (DeudaPago) aún no está en la app; sin marcarlos, el motor los vería como saldo a cuenta y
-- los descontaría de tratamientos nuevos.
BEGIN;
UPDATE pagos SET origen = 'GELITE:PagoCli', origen_fecha = DATE '2026-10-15', updated_at = now()
 WHERE origen IS NULL;
DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos WHERE origen = 'GELITE:PagoCli';
    IF n <> 13948 THEN RAISE EXCEPTION '063: % pagos marcados, se esperaban 13.948', n; END IF;
END $$;
COMMIT;
