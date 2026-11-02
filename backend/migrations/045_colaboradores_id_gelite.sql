-- 045 · Equivalencia de doctores GELITE <-> MakingSmiles (jmd, 17-oct-2026)
-- Los números de doctor NO coinciden entre las dos bases: el IdCol 2 de GELITE es Lucía Guillén
-- y el id 2 de la app es Carolina Nieto. La migración copió el IdCol en bruto, así que la
-- producción quedó atribuida a quien no era. Se deja la equivalencia escrita en la tabla para
-- que no vuelva a pasar: id_gelite = IdCol de TColabos, id_col = id que tiene hoy en la app.
BEGIN;

ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS id_gelite integer;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS id_col    integer;

COMMENT ON COLUMN colaboradores.id_gelite IS 'IdCol en GELITE (TColabos). Origen de la migración.';
COMMENT ON COLUMN colaboradores.id_col    IS 'Id del colaborador en MakingSmiles (= colaboradores.id).';

UPDATE colaboradores SET id_col = id;

UPDATE colaboradores SET id_gelite = v.g FROM (VALUES
    ( 3, 2), ( 4, 3), ( 8, 4), (12, 8), (14,10), (15,11), (16,12),
    (18,14), (19,15), (20,17), (21,18), (22,19), (23,20), (24,21)
) AS v(g, a) WHERE colaboradores.id = v.a;

CREATE UNIQUE INDEX IF NOT EXISTS colaboradores_id_gelite_uq ON colaboradores (id_gelite) WHERE id_gelite IS NOT NULL;

COMMIT;
