-- 01-nov-2026 · Columnas de cefalometría / diagnóstico de CasoOrtodoncia que el MODELO
-- declaraba pero que no existían en la BD (el PR de cefalometría no trajo migración).
--
-- Síntoma: GET /app/doctores/me/pacientes/{id} devolvía 500
--   psycopg.errors.UndefinedColumn: column casos_ortodoncia.mediciones_json does not exist
-- porque el detalle de paciente hace SELECT de casos_ortodoncia con todos los campos.
--
-- Cambio ADITIVO y seguro: solo añade columnas nuevas (IF NOT EXISTS), no toca datos.
ALTER TABLE casos_ortodoncia ADD COLUMN IF NOT EXISTS mediciones_json JSON;
ALTER TABLE casos_ortodoncia ADD COLUMN IF NOT EXISTS diagnostico_texto VARCHAR;
ALTER TABLE casos_ortodoncia ADD COLUMN IF NOT EXISTS diagnostico_clase VARCHAR;
ALTER TABLE casos_ortodoncia ADD COLUMN IF NOT EXISTS diagnostico_patron VARCHAR;
ALTER TABLE casos_ortodoncia ADD COLUMN IF NOT EXISTS plan_tratamiento_json JSON;
