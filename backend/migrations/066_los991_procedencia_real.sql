-- 066 · Procedencia REAL de los 991 pagos: TtosMed (jmd, 17-oct-2026)
-- Paciente, titular, fecha e importe salen de líneas de TtosMed (importe negativo). Se registra su
-- tabla real y su identificador real (TtosMed.Ident). La procedencia NO se muestra en la app.
BEGIN;
CREATE TEMP TABLE _m (id_deuda int, ident int) ON COMMIT DROP;
\copy _m FROM '/tmp/deuda2ident.tsv' WITH (FORMAT text)
UPDATE pagos p SET origen = replace(p.origen, 'GELITE:DeudaCli', 'GELITE:TtosMed'),
                   origen_id_gelite = m.ident::text, updated_at = now()
  FROM _m m
 WHERE p.origen LIKE 'GELITE:DeudaCli (%' AND p.origen_id_gelite = m.id_deuda::text;
COMMENT ON COLUMN pagos.origen_id_gelite IS
 'Identificador real de la fila de origen en GELITE. GELITE:TtosMed (...) → TtosMed.Ident.';
DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos WHERE origen LIKE 'GELITE:TtosMed (%';
    IF n <> 991 THEN RAISE EXCEPTION '066: % filas con TtosMed, se esperaban 991', n; END IF;
END $$;
COMMIT;
