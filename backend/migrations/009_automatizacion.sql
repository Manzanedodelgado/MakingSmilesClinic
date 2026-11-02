-- 009 · Automatización (capa C): log de envíos para idempotencia.
--   Port de automation_sent_log de la .37. Garantiza que un disparador no envíe
--   dos veces al mismo objetivo el mismo día (p.ej. recordatorio_24h de una cita).
CREATE TABLE IF NOT EXISTS envios_automaticos (
  id             SERIAL PRIMARY KEY,
  created_at     TIMESTAMP WITHOUT TIME ZONE,
  updated_at     TIMESTAMP WITHOUT TIME ZONE,
  centro_id      INTEGER NOT NULL REFERENCES centros(id),
  disparador     VARCHAR(60) NOT NULL,        -- recordatorio_24h, cumpleanos…
  clave_objetivo VARCHAR(80) NOT NULL,        -- p.ej. cita:1234 | paciente:4767
  canal          VARCHAR(20) NOT NULL DEFAULT 'whatsapp',
  fecha_envio    DATE NOT NULL,
  paciente_id    INTEGER REFERENCES pacientes(id),
  CONSTRAINT uq_envio_auto UNIQUE (centro_id, disparador, clave_objetivo, fecha_envio)
);
CREATE INDEX IF NOT EXISTS ix_envio_auto_centro ON envios_automaticos (centro_id);
CREATE INDEX IF NOT EXISTS ix_envio_auto_fecha  ON envios_automaticos (fecha_envio);
