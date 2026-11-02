-- 074 · Quitar el coste de laboratorio antiguo (jmd, 17-oct-2026)
-- Paso 2 de 2 de 073. Aplicar SOLO con el backend ya desplegado sin estas columnas en los modelos.
-- Sin pérdida de datos: tratamientos.coste_laboratorio vacío en las 606 filas, genera_coste_lab
-- false en todas, tarifa_precios.coste_laboratorio = 0,00 (615) o NULL (6). Se comprueba antes.
BEGIN;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM tratamientos WHERE coste_laboratorio IS NOT NULL OR genera_coste_lab) THEN
        RAISE EXCEPTION '074: tratamientos tiene costes de laboratorio informados';
    END IF;
    IF EXISTS (SELECT 1 FROM tarifa_precios WHERE COALESCE(coste_laboratorio,0) <> 0) THEN
        RAISE EXCEPTION '074: tarifa_precios tiene costes de laboratorio distintos de 0';
    END IF;
END $$;
ALTER TABLE tratamientos DROP COLUMN coste_laboratorio, DROP COLUMN genera_coste_lab;
ALTER TABLE tarifa_precios DROP COLUMN coste_laboratorio;
COMMIT;
