-- 065 · Volver a añadir a pagos los 991 movimientos negativos de GELITE (jmd, 17-oct-2026)
-- Reglas del usuario: Cobro → pago positivo; Devolución → pago negativo; Descuento y los 3 restantes
-- (traspaso de saldo, colocación ortodoncia autoligable, tratamiento) → positivo, a favor del paciente.
-- Forma 14 (Eurodent): negativos de GELITE anteriores a 2020. Procedencia: su registro de DeudaCli.
BEGIN;
CREATE TEMP TABLE _x (paciente_id int, cliente_id int, fecha date, importe numeric, origen text, id_origen int) ON COMMIT DROP;
\copy _x FROM '/tmp/los991.tsv' WITH (FORMAT text, NULL '\N')
INSERT INTO pagos (created_at, updated_at, centro_id, cliente_id, paciente_id, fecha, importe,
                   forma_pago_id, automatico, anulado, liquidado, origen, origen_id_gelite, origen_fecha)
SELECT now(), now(), 1, cliente_id, paciente_id, fecha, importe, 14, false, false, false,
       origen, id_origen::text, DATE '2026-10-15'
  FROM _x;
DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos WHERE origen LIKE 'GELITE:DeudaCli (%';
    IF n <> 991 THEN RAISE EXCEPTION '065: % filas, se esperaban 991', n; END IF;
END $$;
COMMIT;
