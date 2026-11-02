-- BBDD de PLATAFORMA (makingsmiles_platform) — registro de centros para SuperUser.
-- Se aplica en la BD de plataforma, NUNCA en la operativa de los centros.
CREATE TABLE IF NOT EXISTS platform_centros (
    id SERIAL PRIMARY KEY,
    centro_operativo_id INT NOT NULL UNIQUE,  -- referencia al id en la BD operativa (sin FK cruzada entre BDs)
    nombre TEXT NOT NULL,
    codigo TEXT,
    estado TEXT NOT NULL DEFAULT 'activo',
    plan TEXT,
    modulos_activos JSONB NOT NULL DEFAULT '[]',
    contacto TEXT,
    email TEXT,
    telefono TEXT,
    notas TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_platform_centros_estado ON platform_centros(estado);
