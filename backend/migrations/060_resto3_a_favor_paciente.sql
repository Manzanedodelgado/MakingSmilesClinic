-- 060 · Los 3 negativos restantes de TtosMed, a pagos a favor del paciente (jmd, 17-oct-2026)
-- Orden del usuario: "lo mismo" que los descuentos (059). TRASPASO DE SALDO (434),
-- COLOCACIÓN ORTODONCIA AUTOLIGABLE (183) y TRATAMIENTO (474), con importe negativo en GELITE.
BEGIN;
CREATE TEMP TABLE _r (id_pac int, num_tto int, id_cli int, fecha date, importe numeric, nombre text) ON COMMIT DROP;
\copy _r FROM '/tmp/resto3.tsv' WITH (FORMAT text, NULL '\N')
INSERT INTO pagos (created_at, updated_at, centro_id, cliente_id, paciente_id, fecha, importe,
                   forma_pago_id, automatico, anulado, liquidado, origen, origen_id_gelite, origen_fecha)
SELECT now(), now(), 1, id_cli, id_pac, fecha, importe, 14, false, false, false,
       'GELITE:TtosMed (' || nombre || ')', id_pac || '-' || num_tto, DATE '2026-10-15'
  FROM _r;
COMMIT;
