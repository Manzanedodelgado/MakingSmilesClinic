-- 077 · Quitar tarifa_precios.laboratorio_trabajo_id (jmd, 17-oct-2026)
-- Paso 2 de 2 de 076. Aplicar SOLO con el backend desplegado leyendo tarifa_precio_trabajos.
BEGIN;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM tarifa_precios tp WHERE tp.laboratorio_trabajo_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM tarifa_precio_trabajos x WHERE x.tarifa_precio_id = tp.id
                               AND x.laboratorio_trabajo_id = tp.laboratorio_trabajo_id)) THEN
        RAISE EXCEPTION '077: hay enlaces en tarifa_precios sin pasar a tarifa_precio_trabajos';
    END IF;
END $$;
ALTER TABLE tarifa_precios DROP COLUMN laboratorio_trabajo_id;
COMMIT;
