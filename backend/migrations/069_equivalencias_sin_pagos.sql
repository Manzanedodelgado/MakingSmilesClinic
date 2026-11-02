-- 069 · Quitar de gelite_equivalencias las 14.689 filas de pagos (jmd, 17-oct-2026)
-- Corrección del usuario: esa tabla no es un registro fila a fila. La relación de cada pago con su
-- fila de GELITE ya vive en pagos.origen / pagos.origen_id_gelite. Deshace lo añadido en 067 y 068.
BEGIN;
DELETE FROM gelite_equivalencias WHERE entidad = 'pagos';
DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM gelite_equivalencias WHERE entidad = 'pagos';
    IF n > 0 THEN RAISE EXCEPTION '069: quedan % filas de pagos', n; END IF;
END $$;
COMMIT;
