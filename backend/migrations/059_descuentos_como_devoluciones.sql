-- 059 · Los 54 DESCUENTO de TtosMed, a pagos como devoluciones (jmd, 17-oct-2026)
-- Orden del usuario: "ponlos como devoluciones" = pago en negativo, igual que la 058.
-- Origen: TtosMed StaTto=5, importe negativo, tratamiento 331 "DESCUENTO". En GELITE no apuntan
-- a ningún tratamiento (IdRef, IdPresuTto, Dto vacíos) y su nota es "PAGO: DESCUENTO".
-- AVISO dado al usuario: como pago negativo AUMENTAN la deuda del paciente; en GELITE la reducen.
BEGIN;
CREATE TEMP TABLE _d (id_pac int, num_tto int, id_cli int, fecha date, importe numeric) ON COMMIT DROP;
\copy _d FROM '/tmp/descuentos.tsv' WITH (FORMAT text, NULL '\N')
INSERT INTO pagos (created_at, updated_at, centro_id, cliente_id, paciente_id, fecha, importe,
                   forma_pago_id, automatico, anulado, liquidado, origen, origen_id_gelite, origen_fecha)
SELECT now(), now(), 1, id_cli, id_pac, fecha, importe, 14, false, false, false,
       'GELITE:TtosMed (Descuento como devolución)', id_pac || '-' || num_tto, DATE '2026-10-15'
  FROM _d;
COMMIT;
