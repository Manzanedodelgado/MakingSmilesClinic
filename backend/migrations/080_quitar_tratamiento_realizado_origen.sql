-- 080 · Quitar presupuesto_lineas.tratamiento_realizado_origen_id (jmd, 17-oct-2026)
-- Orden del usuario: un presupuesto recoge lo que hay que hacer; una línea no puede nacer de un
-- tratamiento ya realizado. El enlace válido es tratamientos_realizados.presupuesto_linea_id.
-- Ningún código la usaba; sus 31.506 valores no casaban con el enlace válido. Sin copia (orden de jmd).
BEGIN;
ALTER TABLE presupuesto_lineas DROP COLUMN tratamiento_realizado_origen_id;
COMMIT;
