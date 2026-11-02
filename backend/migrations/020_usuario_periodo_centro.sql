-- C4/C5 (AUDITORIA-CODIGO.md): usuario_periodos no tenía centro_id -> imposible acotar
-- personal/colaboradores por centro sin tocar toda la tabla usuarios (identidad global).
-- Una etapa laboral SÍ pertenece a un centro (es donde trabajó en esas fechas).
-- Idempotente y transaccional. Backfill: hoy solo existe 1 centro en producción, así que
-- se asigna sin ambigüedad; si se añade un 2º centro en el futuro, los periodos nuevos
-- vienen con centro_id explícito desde el router.
BEGIN;

ALTER TABLE usuario_periodos ADD COLUMN IF NOT EXISTS centro_id INTEGER REFERENCES centros(id);

UPDATE usuario_periodos
SET centro_id = (SELECT id FROM centros ORDER BY id LIMIT 1)
WHERE centro_id IS NULL;

-- Solo aprieta a NOT NULL si el backfill dejó todas las filas cubiertas (evita bloquear
-- la migración si algún día hay >1 centro y el backfill de arriba fuese ambiguo).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM usuario_periodos WHERE centro_id IS NULL) THEN
        ALTER TABLE usuario_periodos ALTER COLUMN centro_id SET NOT NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_usuario_periodos_centro_id ON usuario_periodos(centro_id);

COMMIT;
