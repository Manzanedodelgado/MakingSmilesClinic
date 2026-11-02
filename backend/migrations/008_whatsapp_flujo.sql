-- 008 · Estado del flujo conversacional de WhatsApp (máquina de estados, capa A).
--   La .37 lo guardaba en Redis (TTL 30 min). Aquí no hay Redis: el estado del
--   flujo en curso de cada conversación vive en la propia fila, en JSON.
--   {intent, paso, datos, actividad}; NULL = sin flujo en curso.
ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS estado_flujo JSONB;
