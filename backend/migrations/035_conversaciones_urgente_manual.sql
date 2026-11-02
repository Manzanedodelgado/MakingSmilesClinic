-- 035 · Conversaciones: "urgente" pasa a ser SIEMPRE manual (columna dedicada, no la
-- columna `tags` porque ya la usa otra cosa y es de un solo valor). La detección
-- automática por texto (034 la quitó del backend) daba falsos positivos.
ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS urgente BOOLEAN NOT NULL DEFAULT FALSE;
