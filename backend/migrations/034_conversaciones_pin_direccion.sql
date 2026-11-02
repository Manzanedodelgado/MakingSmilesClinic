-- 034 · Conversaciones: fijar (pin) + dirección del último mensaje (para colorear el
-- preview de la lista según si escribió el paciente o el centro, sin parsear texto).
ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS fijada BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS ultima_direccion VARCHAR(10);

-- Backfill: dirección del mensaje más reciente de cada conversación.
UPDATE conversaciones c SET ultima_direccion = m.direccion
FROM (
    SELECT DISTINCT ON (conversacion_id) conversacion_id, direccion
    FROM mensajes
    ORDER BY conversacion_id, enviado_at DESC, id DESC
) m
WHERE m.conversacion_id = c.id AND c.ultima_direccion IS NULL;
