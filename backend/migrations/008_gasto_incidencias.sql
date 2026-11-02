-- 008 · Incidencias de ingesta de facturas (triage del buzón).
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS incidencia VARCHAR(200);
CREATE TABLE IF NOT EXISTS gasto_incidencias (
  id          SERIAL PRIMARY KEY,
  created_at  TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
  updated_at  TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
  centro_id   INTEGER NOT NULL REFERENCES centros(id),
  gmail_message_id VARCHAR(120),
  fecha       DATE,
  remitente   VARCHAR(300),
  asunto      VARCHAR(400),
  motivo      VARCHAR(200) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_gasto_incid_centro ON gasto_incidencias (centro_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_gasto_incid_msg ON gasto_incidencias (gmail_message_id) WHERE gmail_message_id IS NOT NULL;
