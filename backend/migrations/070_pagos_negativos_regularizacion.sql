-- 070 · Añadir a pagos los 250 pagos negativos de GELITE como Regularización (jmd, 17-oct-2026)
-- Orden del usuario: anotarlos como regularización → forma 17 "Regularización Master Dental".
-- Importe negativo tal cual en GELITE. Procedencia GELITE:PagoCli + IdPagoCli.
BEGIN;
CREATE TEMP TABLE _g (paciente_id int, cliente_id int, fecha date, importe numeric, forma int,
                      anulado boolean, automatico boolean, num_recibo text, num_factura text,
                      num_transaccion text, id_pagocli int) ON COMMIT DROP;
\copy _g FROM '/tmp/pagocli.tsv' WITH (FORMAT text, NULL '\N')
INSERT INTO pagos (created_at, updated_at, centro_id, cliente_id, paciente_id, fecha, importe,
                   forma_pago_id, automatico, anulado, liquidado, num_recibo, num_factura,
                   num_transaccion, origen, origen_id_gelite, origen_fecha)
SELECT now(), now(), 1, cliente_id, paciente_id, fecha, importe, 17, automatico, anulado, false,
       num_recibo, num_factura, num_transaccion, 'GELITE:PagoCli', id_pagocli::text, DATE '2026-10-15'
  FROM _g WHERE importe < 0;
DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos WHERE origen = 'GELITE:PagoCli';
    IF n <> 13948 THEN RAISE EXCEPTION '070: % pagos de PagoCli, se esperaban 13.948', n; END IF;
END $$;
COMMIT;
