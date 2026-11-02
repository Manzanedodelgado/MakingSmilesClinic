-- 050 · Marcar cuáles de las notas importadas por la 044 son dudosas (jmd, 17-oct-2026)
--
-- La 044 importó 1.382 líneas de GELITE como actos de REVISIÓN. Qué líneas entraban lo decidió
-- un filtro sobre TEXTO LIBRE escrito a mano por el mostrador, que NO es un criterio verificable:
-- se colaron anotaciones de cobro ("MENSU", "PAGA LIMPIEZA", "Abono para regularizar saldo").
--
-- Contraste estructural contra GELITE (PagoCli, mismo titular y mismo día):
--   · 10.021 de las 10.297 financieras por texto (97%) tienen un pago ese día → no se importaron, correcto.
--   · De las 1.390 importables, 450 coinciden con un pago ese día → MEZCLA: hay notas clínicas
--     legítimas y hay apuntes de cobro. Coincidir con un pago no prueba nada (el paciente suele
--     pagar el día que viene), así que NO hay regla automática que las separe.
--
-- Esta migración no borra ni cambia ningún dato: deja la incertidumbre ESCRITA en la base,
-- para que nadie dé por clínicas las 1.382 sin saber que 450 están sin confirmar.
BEGIN;

ALTER TABLE tratamientos_realizados_ids_044
    ADD COLUMN IF NOT EXISTS coincide_con_pago boolean,
    ADD COLUMN IF NOT EXISTS revisar           boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS revisado_por      text;

COMMENT ON TABLE tratamientos_realizados_ids_044 IS
 'Notas de GELITE importadas como REVISIÓN (migración 044). revisar=true: la línea coincide con '
 'un pago del mismo titular ese mismo día, así que puede ser un apunte de cobro y no una nota '
 'clínica. Clasificación hecha sobre texto libre: NO es verificable sin revisión humana.';

CREATE TEMP TABLE _rev (id_pac int, num_tto int, hay_pago int) ON COMMIT DROP;
\copy _rev FROM '/tmp/revisar_044.tsv' WITH (FORMAT text)

UPDATE tratamientos_realizados_ids_044 i
   SET coincide_con_pago = (v.hay_pago = 1),
       revisar           = (v.hay_pago = 1)
  FROM tratamientos_realizados r
  JOIN _rev v ON v.id_pac = r.paciente_id AND v.num_tto = r.num_tto
 WHERE r.id = i.id;

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM tratamientos_realizados_ids_044 WHERE coincide_con_pago IS NULL;
    IF n > 0 THEN RAISE EXCEPTION '050: % notas quedaron sin marcar', n; END IF;
END $$;

COMMIT;
