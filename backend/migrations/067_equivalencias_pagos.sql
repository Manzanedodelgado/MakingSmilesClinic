-- 067 · Registrar en gelite_equivalencias los dos ids de cada pago (jmd, 17-oct-2026)
-- id_gelite = TtosMed.Ident (fila de origen) · id_app = pagos.id
BEGIN;
INSERT INTO gelite_equivalencias (entidad, id_gelite, nombre_gelite, id_app, nombre_app, estado, filas_usando, revisado, nota)
SELECT 'pagos', origen_id_gelite::int, origen, id,
       'pago ' || id || ' · paciente ' || paciente_id || ' · ' || fecha || ' · ' || importe || ' €',
       'DISTINTO', 1, true, 'Pago migrado desde una línea de TtosMed con importe negativo.'
  FROM pagos WHERE origen LIKE 'GELITE:TtosMed (%';
DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM gelite_equivalencias WHERE entidad = 'pagos';
    IF n <> 991 THEN RAISE EXCEPTION '067: % filas de pagos, se esperaban 991', n; END IF;
END $$;
COMMIT;
