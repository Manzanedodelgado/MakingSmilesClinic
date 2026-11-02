-- 058 · Cobros y devoluciones de TtosMed a pagos (jmd, 17-oct-2026)
-- Orden del usuario: "Los que sean cobro se tratarán como un pago, devoluciones como un pago en
-- negativo." Origen: TtosMed StaTto=5, importe negativo, tratamiento 522 "Cobro" o 448 "DEVOLUCIÓN".
-- Cobro → pago en positivo. Devolución → pago en negativo. Paciente, titular y fecha de GELITE.
-- Forma de pago 14 (Eurodent) por la regla del usuario: negativo de GELITE hasta 31-12-2019 =
-- Eurodent; todas son anteriores a esa fecha.
BEGIN;

ALTER TABLE pagos
    ADD COLUMN IF NOT EXISTS origen           text,
    ADD COLUMN IF NOT EXISTS origen_id_gelite text,
    ADD COLUMN IF NOT EXISTS origen_fecha     date;

CREATE TEMP TABLE _cd (id_pac int, num_tto int, id_cli int, fecha date, importe numeric, id_trat int) ON COMMIT DROP;
\copy _cd FROM '/tmp/cobros_dev.tsv' WITH (FORMAT text, NULL '\N')

INSERT INTO pagos (created_at, updated_at, centro_id, cliente_id, paciente_id, fecha, importe,
                   forma_pago_id, automatico, anulado, liquidado,
                   origen, origen_id_gelite, origen_fecha)
SELECT now(), now(), 1, id_cli, id_pac, fecha, importe, 14, false, false, false,
       CASE id_trat WHEN 522 THEN 'GELITE:TtosMed (Cobro)' ELSE 'GELITE:TtosMed (Devolución)' END,
       id_pac || '-' || num_tto, DATE '2026-10-15'
  FROM _cd;

COMMIT;
