-- 054 · Corregir la 053, que asignó a Lucía 1.669 actos en vez de 71 (jmd, 17-oct-2026)
-- La 053 seleccionaba "todas las filas sin doctor" en lugar de "las del IdCol 6 de GELITE".
-- Se devuelven a NULL las que en GELITE tampoco tienen doctor y se deja a Lucía SOLO el IdCol 6.
BEGIN;

CREATE TEMP TABLE _c6 (id_pac int, num_tto int) ON COMMIT DROP;
\copy _c6 FROM '/tmp/idcol6.tsv' WITH (FORMAT text)

UPDATE tratamientos_realizados r SET colaborador_id = NULL, updated_at = now()
 WHERE r.id IN (SELECT id FROM tratamientos_realizados_colab_bk_053)
   AND NOT EXISTS (SELECT 1 FROM _c6 c WHERE c.id_pac = r.paciente_id AND c.num_tto = r.num_tto);

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM tratamientos_realizados r
      JOIN tratamientos_realizados_colab_bk_053 b ON b.id = r.id
     WHERE r.colaborador_id IS NOT NULL;
    IF n <> 71 THEN RAISE EXCEPTION '054: Lucía se queda con % actos, se esperaban 71', n; END IF;
END $$;

COMMIT;
