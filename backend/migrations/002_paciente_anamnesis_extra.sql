-- Fase 2 · Filiación completa del paciente
-- Añade a `pacientes` dos columnas JSONB para cubrir el gap del módulo Pacientes:
--   anamnesis    = lista de ítems clínicos marcados (el CATÁLOGO vive en CONFIG: clinica.anamnesis)
--   datos_extra  = bolsa key/valor de filiación (seguro, responsable, facturación, datos médicos…)
-- SOAP por acto NO necesita migración: ya existe la tabla `soap`.
-- Idempotente y transaccional. No toca datos existentes.
BEGIN;

ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS anamnesis   JSONB;
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS datos_extra JSONB;

COMMIT;
