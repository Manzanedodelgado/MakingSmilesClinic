-- 061 · En pagos, origen_id_gelite pasa de 'IdPac-NumTto' a TtosMed.Ident (jmd, 17-oct-2026)
-- Corrección del usuario: IdPac se mantiene (es el mismo paciente_id de la app), pero NumTto es
-- el número de línea de TRATAMIENTO en GELITE, y en la app estos registros NO son tratamientos,
-- son pagos: NumTto no significa nada aquí. El identificador de la fila de origen es
-- TtosMed.Ident, único en toda la tabla (57.877 de 57.877) y el que usa GELITE para enlazar
-- (DeudaCli.IdentTM, PagoCli.IdentTM).
BEGIN;
CREATE TEMP TABLE _m (clave_vieja text, ident int) ON COMMIT DROP;
\copy _m FROM '/tmp/ident991.tsv' WITH (FORMAT text)

UPDATE pagos p SET origen_id_gelite = m.ident::text, updated_at = now()
  FROM _m m
 WHERE p.origen LIKE 'GELITE:TtosMed (%' AND p.origen_id_gelite = m.clave_vieja;

COMMENT ON COLUMN pagos.origen_id_gelite IS
 'Identificador de la fila de origen en GELITE. Para origen GELITE:TtosMed (...) es TtosMed.Ident.';

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos WHERE origen LIKE 'GELITE:TtosMed (%' AND origen_id_gelite LIKE '%-%';
    IF n > 0 THEN RAISE EXCEPTION '061: quedan % con la clave vieja IdPac-NumTto', n; END IF;
END $$;
COMMIT;
