-- 010 · Voicebot: registro de llamadas de voz. Port de voicebotCall (.37).
--   El canal de voz reutiliza el agente Alex: el AGI/pasarela telefónica manda el
--   turno (texto transcrito) y aquí se registra entrada/respuesta para historial y
--   métricas. La config SIP vive en `integraciones` tipo='voicebot_sip' (CanalesIA).
CREATE TABLE IF NOT EXISTS llamadas_voz (
  id           SERIAL PRIMARY KEY,
  created_at   TIMESTAMP WITHOUT TIME ZONE,
  updated_at   TIMESTAMP WITHOUT TIME ZONE,
  centro_id    INTEGER NOT NULL REFERENCES centros(id),
  paciente_id  INTEGER REFERENCES pacientes(id),
  telefono     VARCHAR(50),
  entrada      VARCHAR(2000),     -- lo que dijo el paciente (transcrito)
  respuesta    VARCHAR(2000),     -- lo que respondió el agente
  duracion_seg INTEGER,
  estado       VARCHAR(20) NOT NULL DEFAULT 'finalizada'   -- en_curso | finalizada | fallida
);
CREATE INDEX IF NOT EXISTS ix_llamada_voz_centro   ON llamadas_voz (centro_id);
CREATE INDEX IF NOT EXISTS ix_llamada_voz_paciente ON llamadas_voz (paciente_id);
CREATE INDEX IF NOT EXISTS ix_llamada_voz_fecha    ON llamadas_voz (created_at);
