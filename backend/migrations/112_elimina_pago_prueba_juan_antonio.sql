-- 30-oct-2026: pago 31338 (18-10-2026, 1.000 €, Cetelem, paciente JUAN ANTONIO MANZANEDO DELGADO) era una prueba (indicado por el usuario).
-- Sin pago_tratamiento, deuda_pago ni apunte bancario asociados.
DELETE FROM pagos WHERE id = 31338 AND paciente_id = 4767 AND importe = 1000.00 AND fecha = DATE '2026-10-18';
