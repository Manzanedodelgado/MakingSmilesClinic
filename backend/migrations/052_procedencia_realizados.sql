-- 052 · Marcar la procedencia de los tratamientos realizados (jmd, 17-oct-2026)
-- Norma del usuario: todo dato traído de GELITE se etiqueta en su propia fila, no en una tabla
-- aparte. Hasta ahora no se etiquetaba nada, y por eso el IdCol de GELITE se guardó en
-- colaborador_id como si fuera un id de la app, atribuyendo la producción a quien no era.
BEGIN;

ALTER TABLE tratamientos_realizados
    ADD COLUMN IF NOT EXISTS origen           text,     -- 'GELITE:TtosMed' | NULL = nacido en la app
    ADD COLUMN IF NOT EXISTS origen_id_gelite text,     -- clave en el origen: IdPac-NumTto
    ADD COLUMN IF NOT EXISTS origen_fecha     date;     -- fecha de la copia de GELITE usada

COMMENT ON COLUMN tratamientos_realizados.origen IS
 'De dónde vino la fila. GELITE:TtosMed = copiada de TtosMed (StaTto=5). NULL = creada en la app.';
COMMENT ON COLUMN tratamientos_realizados.origen_id_gelite IS
 'Clave en el origen: IdPac-NumTto de TtosMed. Permite recontrastar fila a fila.';

-- Las 39.487 escritas por la 051 desde la copia de GELITE del 15-oct-2026.
UPDATE tratamientos_realizados r
   SET origen = 'GELITE:TtosMed',
       origen_id_gelite = r.paciente_id || '-' || r.num_tto,
       origen_fecha = DATE '2026-10-15'
 WHERE r.id NOT IN (SELECT id FROM tratamientos_realizados_ids_044);

-- Las 1.382 notas: también de TtosMed, pero de las líneas SIN tratamiento (IdTto NULL).
UPDATE tratamientos_realizados r
   SET origen = 'GELITE:TtosMed (nota sin tratamiento)',
       origen_id_gelite = r.paciente_id || '-' || r.num_tto,
       origen_fecha = DATE '2026-10-15'
  FROM tratamientos_realizados_ids_044 i
 WHERE i.id = r.id;

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM tratamientos_realizados WHERE origen IS NULL;
    IF n > 0 THEN RAISE EXCEPTION '052: quedan % filas sin procedencia', n; END IF;
END $$;

COMMIT;
