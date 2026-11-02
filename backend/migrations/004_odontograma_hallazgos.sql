-- Odontograma editable (hallazgos) — campos para portar el editor del .37.
--   obs            = descripción/tratamiento libre del hallazgo
--   tipo_registro  = INICIAL | REALIZADO | PRESUPUESTADO  (Máquina del Tiempo)
-- Idempotente y transaccional.
BEGIN;

ALTER TABLE odontograma_entradas ADD COLUMN IF NOT EXISTS obs VARCHAR(500);
ALTER TABLE odontograma_entradas ADD COLUMN IF NOT EXISTS tipo_registro VARCHAR(20) NOT NULL DEFAULT 'INICIAL';

COMMIT;
