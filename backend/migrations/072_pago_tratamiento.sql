-- 072 · Asociación pago → tratamiento realizado por importe y fecha (jmd, 17-oct-2026)
-- Orden del usuario: asociar cada pago a un tratamiento según importe y fecha, salvo los que no
-- casan con nada (quedan sin asociar = a cuenta). Un pago puede ir a varios tratamientos.
-- `metodo` dice cómo se emparejó (acierto medido contra el reparto real de GELITE):
--   importe_fecha_unico    mismo importe y fecha, un candidato   (~96 %)
--   suma_mismo_dia         suma de varios tratamientos del día   (~92 %)
--   importe_fecha_varios   mismo importe y fecha, varios         (~44 %)
--   importe_fecha_cercana  mismo importe, ±60 días               (~51 %)
-- Regla: lo asignado a un tratamiento nunca supera su importe.
BEGIN;
CREATE TABLE IF NOT EXISTS pago_tratamiento (
    id                       serial PRIMARY KEY,
    created_at               timestamp NOT NULL DEFAULT now(),
    pago_id                  integer NOT NULL REFERENCES pagos(id),
    tratamiento_realizado_id integer NOT NULL REFERENCES tratamientos_realizados(id),
    importe                  numeric(12,2) NOT NULL CHECK (importe > 0),
    metodo                   text NOT NULL,
    UNIQUE (pago_id, tratamiento_realizado_id)
);
CREATE INDEX IF NOT EXISTS ix_pago_tratamiento_tto ON pago_tratamiento (tratamiento_realizado_id);
COMMENT ON TABLE pago_tratamiento IS 'Qué tratamiento realizado paga cada pago y por cuánto. metodo = cómo se asoció.';

CREATE TEMP TABLE _x (pago_id int, tto_id int, importe numeric, metodo text) ON COMMIT DROP;
\copy _x FROM '/tmp/pago_tto.tsv' WITH (FORMAT text)
INSERT INTO pago_tratamiento (pago_id, tratamiento_realizado_id, importe, metodo)
SELECT pago_id, tto_id, importe, metodo FROM _x;

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM (
      SELECT pt.tratamiento_realizado_id FROM pago_tratamiento pt
        JOIN tratamientos_realizados r ON r.id = pt.tratamiento_realizado_id
       GROUP BY pt.tratamiento_realizado_id, r.importe HAVING sum(pt.importe) > r.importe + 0.005) z;
    IF n > 0 THEN RAISE EXCEPTION '072: % tratamientos reciben más que su importe', n; END IF;
    SELECT count(*) INTO n FROM (
      SELECT pt.pago_id FROM pago_tratamiento pt JOIN pagos p ON p.id = pt.pago_id
       GROUP BY pt.pago_id, p.importe HAVING sum(pt.importe) > p.importe + 0.005) z;
    IF n > 0 THEN RAISE EXCEPTION '072: % pagos reparten más que su importe', n; END IF;
    SELECT count(*) INTO n FROM pago_tratamiento pt JOIN pagos p ON p.id=pt.pago_id
      JOIN tratamientos_realizados r ON r.id=pt.tratamiento_realizado_id WHERE p.paciente_id <> r.paciente_id;
    IF n > 0 THEN RAISE EXCEPTION '072: % enlaces entre pacientes distintos', n; END IF;
END $$;
COMMIT;
