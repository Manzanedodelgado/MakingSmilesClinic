-- Prepara agente_revisiones para el Plan 3 (entrenamiento ligado a la tabla
-- `agentes` nueva, en vez de solo al string `agente`). Nullable: no se rompe
-- nada de lo que ya lee esta tabla hoy; se rellena cuando el Plan 3 conecte
-- el entrenamiento real.
--
-- IMPORTANTE: requiere que la tabla `agentes` ya exista (la crea
-- SQLModel.metadata.create_all() al arrancar la app, no un fichero de
-- migración) — aplicar esta migración solo DESPUÉS de desplegar la versión
-- que introduce esa tabla, o fallará con "relation agentes does not exist".
--
-- Rollback si hace falta:
--   DROP INDEX IF EXISTS ix_agente_revisiones_agente_id;
--   ALTER TABLE agente_revisiones DROP COLUMN IF EXISTS agente_id;
BEGIN;

ALTER TABLE agente_revisiones ADD COLUMN IF NOT EXISTS agente_id INT REFERENCES agentes(id);
CREATE INDEX IF NOT EXISTS ix_agente_revisiones_agente_id ON agente_revisiones(agente_id);

COMMIT;
