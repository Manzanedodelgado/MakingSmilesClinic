-- 044 · Recuperar las anotaciones de GELITE que la migración descartó (jmd, 17-oct-2026)
-- En GELITE (TtosMed, StaTto=5) hay 11.699 filas con IdTto NULL: líneas de solo texto, sin
-- tratamiento, sin pieza y sin importe. La migración las descartó por no tener tratamiento.
-- De ellas, 10.315 son anotaciones de cobros/pagos (no se recuperan) y 1.382 son notas
-- clínicas y de seguimiento del paciente (urgencias, pruebas, llamadas, reclamaciones).
-- Decisión del usuario: se asocian al tratamiento "REVISIÓN" (id 615, código REVI).
-- Se conserva su paciente (IdPac), su nº de tratamiento (NumTto), su doctor (IdCol),
-- sus fechas y su texto íntegro. Importe 0, estado 5 (Realizado), como en el origen.
BEGIN;

CREATE TEMP TABLE _carga_044 (
    centro_id int, paciente_id int, num_tto int, tratamiento_id int, colaborador_id int,
    fecha_inicio date, fecha_fin date, importe numeric, estado_id int, notas text
) ON COMMIT DROP;

\copy _carga_044 FROM '/tmp/044_rows.sql' WITH (FORMAT text, NULL '\N')

CREATE TABLE IF NOT EXISTS tratamientos_realizados_ids_044 (id bigint primary key);

WITH nuevas AS (
    INSERT INTO tratamientos_realizados
        (created_at, updated_at, centro_id, paciente_id, num_tto, tratamiento_id,
         colaborador_id, fecha_inicio, fecha_fin, importe, estado_id, notas)
    SELECT now(), now(), c.centro_id, c.paciente_id, c.num_tto, c.tratamiento_id,
           c.colaborador_id, c.fecha_inicio, c.fecha_fin, c.importe, c.estado_id, c.notas
      FROM _carga_044 c
    RETURNING id
)
INSERT INTO tratamientos_realizados_ids_044 (id) SELECT id FROM nuevas;

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM tratamientos_realizados_ids_044;
    IF n <> 1382 THEN RAISE EXCEPTION '044: se esperaban 1382 filas, hay %', n; END IF;
END $$;

COMMIT;
