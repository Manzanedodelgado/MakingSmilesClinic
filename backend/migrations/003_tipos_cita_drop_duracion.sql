-- 003 · La duración de cita NO pertenece al tipo de cita: la dicta cada
-- colaborador. Se elimina la columna duracion_default_min de tipos_cita.
ALTER TABLE tipos_cita DROP COLUMN IF EXISTS duracion_default_min;
