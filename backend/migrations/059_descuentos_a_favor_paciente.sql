-- 059 · Los 54 DESCUENTO de TtosMed, a pagos A FAVOR del paciente (jmd, 17-oct-2026)
-- Orden del usuario: ponerlos a favor del paciente = importe positivo en pagos, rebajan su deuda,
-- igual que en GELITE. Origen: TtosMed StaTto=5, importe negativo, tratamiento 331 "DESCUENTO".
-- En GELITE no apuntan a ningún tratamiento (IdRef, IdPresuTto, Dto vacíos); nota "PAGO: DESCUENTO".
BEGIN;
CREATE TEMP TABLE _d (id_pac int, num_tto int, id_cli int, fecha date, importe numeric) ON COMMIT DROP;
\copy _d FROM '/tmp/descuentos.tsv' WITH (FORMAT text, NULL '\N')
INSERT INTO pagos (created_at, updated_at, centro_id, cliente_id, paciente_id, fecha, importe,
                   forma_pago_id, automatico, anulado, liquidado, origen, origen_id_gelite, origen_fecha)
SELECT now(), now(), 1, id_cli, id_pac, fecha, importe, 14, false, false, false,
       'GELITE:TtosMed (Descuento)', id_pac || '-' || num_tto, DATE '2026-10-15'
  FROM _d;
COMMIT;
