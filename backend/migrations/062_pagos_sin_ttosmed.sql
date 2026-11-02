-- 062 · Quitar de pagos toda referencia a TtosMed (jmd, 17-oct-2026)
-- Orden del usuario: en pagos no debe aparecer nada de tratamientos. La procedencia pasa a su
-- registro en DeudaCli (el cargo que GELITE tiene de cada uno; 1 a 1 con los 991, verificado).
--   origen           'GELITE:TtosMed (Cobro)'  ->  'GELITE:DeudaCli (Cobro)'
--   origen_id_gelite  TtosMed.Ident            ->  DeudaCli.IdDeudaCli
BEGIN;
CREATE TEMP TABLE _m (ident int, id_deuda int) ON COMMIT DROP;
\copy _m FROM '/tmp/ident_deuda.tsv' WITH (FORMAT text)

UPDATE pagos p SET origen_id_gelite = m.id_deuda::text,
                   origen = replace(p.origen, 'GELITE:TtosMed', 'GELITE:DeudaCli'),
                   updated_at = now()
  FROM _m m
 WHERE p.origen LIKE 'GELITE:TtosMed (%' AND p.origen_id_gelite = m.ident::text;

COMMENT ON COLUMN pagos.origen_id_gelite IS
 'Identificador del registro de origen en GELITE. Para origen GELITE:DeudaCli (...) es DeudaCli.IdDeudaCli.';

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos WHERE origen ILIKE '%ttos%';
    IF n > 0 THEN RAISE EXCEPTION '062: quedan % pagos con referencia a TtosMed', n; END IF;
    SELECT count(*) INTO n FROM pagos WHERE origen LIKE 'GELITE:DeudaCli (%';
    IF n <> 991 THEN RAISE EXCEPTION '062: % pagos con DeudaCli, se esperaban 991', n; END IF;
END $$;
COMMIT;
