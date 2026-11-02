-- 055 · Sacar de tratamientos_realizados las 1.382 notas que metió la 044 (jmd, 17-oct-2026)
--
-- No son tratamientos: en GELITE son líneas de TtosMed con IdTto NULL, sin tratamiento, sin
-- pieza y sin importe. Las importé con un filtro sobre texto libre, que no es un criterio
-- verificable, y el resultado es que dentro hay apuntes de cobro: 446 coinciden con un pago
-- del mismo día y otras 111 hablan de dinero sin coincidir ("ACORDAMOS EL PAGO MENSUAL DE 740
-- EUROS", "pendiente 400 euros abona en Julio").
--
-- La tabla queda EXACTAMENTE con lo que GELITE tiene como realizado: 39.487 filas.
-- El texto no se pierde: queda en notas_gelite_sin_tratamiento para decidir dónde va.
BEGIN;

CREATE TABLE IF NOT EXISTS notas_gelite_sin_tratamiento AS
    SELECT r.*, i.coincide_con_pago, i.revisar
      FROM tratamientos_realizados r
      JOIN tratamientos_realizados_ids_044 i ON i.id = r.id;

COMMENT ON TABLE notas_gelite_sin_tratamiento IS
 'Las 1.382 líneas de texto de GELITE (TtosMed con IdTto NULL) que estuvieron por error en '
 'tratamientos_realizados el 17-oct-2026. Mezclan notas clínicas y apuntes de cobro; NINGUNA '
 'está verificada. Pendiente decidir su destino. No son tratamientos.';

DELETE FROM tratamientos_realizados
 WHERE id IN (SELECT id FROM tratamientos_realizados_ids_044);

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM tratamientos_realizados;
    IF n <> 39487 THEN RAISE EXCEPTION '055: quedan % filas, se esperaban 39.487', n; END IF;
    SELECT count(*) INTO n FROM tratamientos_realizados WHERE origen <> 'GELITE:TtosMed';
    IF n > 0 THEN RAISE EXCEPTION '055: quedan % filas que no son de TtosMed', n; END IF;
END $$;

COMMIT;
