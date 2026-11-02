-- Asociación entre centros (SuperUser → "Nuevo centro" → asociado a otro).
-- Cada centro asociado elige INDEPENDIENTEMENTE qué comparte con el centro al que se asocia:
--   comparte_personal      → el personal YA existente del centro asociado recibe acceso
--                            también a este centro (misma identidad global en `usuarios`,
--                            nunca se duplica — ver user_center_roles/user_center_permisos).
--   comparte_razon_social  → este centro NO tiene razón social propia; usa la del centro
--                            asociado para facturación (ver centros.razon_social_compartida_id).
--   comparte_pacientes     → guardado aquí para cuando se construya el acceso cruzado a
--                            pacientes (dato clínico/RGPD) — NO implementado todavía, la
--                            aplicación aún no concede visibilidad cruzada por este flag.
-- Idempotente y transaccional.
BEGIN;

CREATE TABLE IF NOT EXISTS centro_asociaciones (
    id BIGSERIAL PRIMARY KEY,
    centro_id INTEGER NOT NULL REFERENCES centros(id),
    asociado_a_centro_id INTEGER NOT NULL REFERENCES centros(id),
    comparte_personal BOOLEAN NOT NULL DEFAULT false,
    comparte_razon_social BOOLEAN NOT NULL DEFAULT false,
    comparte_pacientes BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT centro_asociaciones_no_self CHECK (centro_id <> asociado_a_centro_id),
    CONSTRAINT centro_asociaciones_unica UNIQUE (centro_id, asociado_a_centro_id)
);
CREATE INDEX IF NOT EXISTS ix_centro_asociaciones_centro_id ON centro_asociaciones(centro_id);
CREATE INDEX IF NOT EXISTS ix_centro_asociaciones_asociado_a ON centro_asociaciones(asociado_a_centro_id);

ALTER TABLE centros ADD COLUMN IF NOT EXISTS razon_social_compartida_id INTEGER REFERENCES razones_sociales(id);

COMMIT;
