-- 042 · Sacar de tratamientos_realizados los cobros/descuentos de la aplicación anterior (jmd, 17-oct-2026)
-- 991 filas con importe NEGATIVO (2014-2016) eran cobros ("Cobro", nota "PAGO: Cobro"), descuentos,
-- devoluciones y un traspaso de saldo que la aplicación anterior a Gesden metió como "tratamientos"
-- (con un cargo negativo en DeudaCli). Restaban del importe realizado (−239.095,85 €) y de la
-- PRODUCCIÓN de los doctores a los que estaban asignadas. No son tratamientos.
--   · Cobro / DEVOLUCIÓN / TRASPASO DE SALDO → pagos con forma 17 "Cobro de la aplicación anterior".
--   · DESCUENTO y el resto de negativos     → pagos con forma 18 "Descuento de la aplicación anterior".
--   Importe del pago = −importe del tratamiento: la deuda del paciente (realizado − pagado) no cambia.
--   num_transaccion = 'TR<id>' conserva la trazabilidad con la fila original.
-- Copia íntegra previa en tratamientos_realizados_bk_042 / tratamientos_realizados_fases_bk_042 y
-- en presupuesto_lineas_origen_bk_042 (enlaces que se quitan). Se ejecuta una sola vez.
BEGIN;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tratamientos_realizados_bk_042') THEN
        RAISE EXCEPTION '042 ya aplicada (existe tratamientos_realizados_bk_042)';
    END IF;
END $$;

CREATE TABLE tratamientos_realizados_bk_042 AS SELECT * FROM tratamientos_realizados WHERE importe < 0;
CREATE TABLE tratamientos_realizados_fases_bk_042 AS
    SELECT * FROM tratamientos_realizados_fases WHERE tratamiento_realizado_id IN (SELECT id FROM tratamientos_realizados_bk_042);
CREATE TABLE presupuesto_lineas_origen_bk_042 AS
    SELECT id, tratamiento_realizado_origen_id FROM presupuesto_lineas
     WHERE tratamiento_realizado_origen_id IN (SELECT id FROM tratamientos_realizados_bk_042);

INSERT INTO formas_pago (id, codigo, nombre, grupo, en_caja, orden) VALUES
    (17, NULL, 'Cobro de la aplicación anterior',     'Aplicación anterior', false, 300),
    (18, NULL, 'Descuento de la aplicación anterior', 'Descuento',           false, 310)
ON CONFLICT (id) DO NOTHING;

INSERT INTO pagos (created_at, updated_at, centro_id, cliente_id, paciente_id, fecha, importe,
                   forma_pago_id, num_transaccion, automatico, anulado, liquidado)
SELECT now(), now(), r.centro_id, r.cliente_id, r.paciente_id, coalesce(r.fecha_fin, r.fecha_inicio),
       -r.importe,
       CASE WHEN t.nombre IN ('Cobro', 'DEVOLUCIÓN', 'TRASPASO DE SALDO') THEN 17 ELSE 18 END,
       'TR' || r.id, false, false, false
  FROM tratamientos_realizados_bk_042 r
  LEFT JOIN tratamientos t ON t.id = r.tratamiento_id;

UPDATE presupuesto_lineas SET tratamiento_realizado_origen_id = NULL
 WHERE id IN (SELECT id FROM presupuesto_lineas_origen_bk_042);
DELETE FROM tratamientos_realizados_fases WHERE tratamiento_realizado_id IN (SELECT id FROM tratamientos_realizados_bk_042);
DELETE FROM tratamientos_realizados WHERE id IN (SELECT id FROM tratamientos_realizados_bk_042);

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM tratamientos_realizados WHERE importe < 0;
    IF n > 0 THEN RAISE EXCEPTION '042: quedan % realizados con importe negativo', n; END IF;
END $$;

COMMIT;
