-- Modelo de IA por agente: permite que Alex, La Consulta Viva y el Gestor IA (gastos y
-- facturas) usen cada uno el modelo más adecuado, en vez de un único LLM compartido.
-- `agente` solo se usa cuando tipo='llm'; NULL en el resto de tipos (whatsapp, voicebot_sip,
-- email_*) sin cambio de comportamiento. Con agente=NULL en una fila 'llm' se sigue leyendo
-- como el modelo compartido de siempre (retrocompatible: nada se rompe si no se configura
-- ningún slot nuevo).
BEGIN;

ALTER TABLE integraciones ADD COLUMN IF NOT EXISTS agente VARCHAR(40);

COMMIT;
