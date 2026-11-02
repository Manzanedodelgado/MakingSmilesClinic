-- Chat IA (entrenamiento por agente): agente_revisiones gana `agente` para no mezclar
-- correcciones entre Alex/Gestor IA/etc., y conversacion_id/telefono se hacen opcionales
-- porque el Chat IA de entrenamiento no está atado a una conversación real de WhatsApp
-- (a diferencia de la Bandeja IA, que sí lo estaba).
BEGIN;

ALTER TABLE agente_revisiones ADD COLUMN IF NOT EXISTS agente VARCHAR(40) NOT NULL DEFAULT 'alex';
ALTER TABLE agente_revisiones ALTER COLUMN conversacion_id DROP NOT NULL;
ALTER TABLE agente_revisiones ALTER COLUMN telefono DROP NOT NULL;

COMMIT;
