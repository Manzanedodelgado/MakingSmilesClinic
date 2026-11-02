-- 005 · Filiación normalizada: cada bloque de la bolsa datos_extra a su tabla.
--   Facturación → clientes (ya existía; + forma_pago / titular_cuenta)
--   Responsable + Datos médicos → columnas en pacientes
--   Seguro → tabla nueva paciente_seguros
ALTER TABLE clientes  ADD COLUMN IF NOT EXISTS titular_cuenta VARCHAR(200);
ALTER TABLE clientes  ADD COLUMN IF NOT EXISTS forma_pago     VARCHAR(60);

ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS responsable_nombre     VARCHAR(200);
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS responsable_nif        VARCHAR(20);
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS responsable_parentesco VARCHAR(60);
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS grupo_sanguineo        VARCHAR(8);
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS peso                   DOUBLE PRECISION;
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS altura                 DOUBLE PRECISION;
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS medico_cabecera        VARCHAR(200);
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS tel_medico             VARCHAR(50);
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS especialista           VARCHAR(200);

CREATE TABLE IF NOT EXISTS paciente_seguros (
  id          SERIAL PRIMARY KEY,
  created_at  TIMESTAMP WITHOUT TIME ZONE,
  updated_at  TIMESTAMP WITHOUT TIME ZONE,
  paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
  aseguradora VARCHAR(160),
  num_poliza  VARCHAR(80),
  num_ss      VARCHAR(40),
  activo      BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_paciente_seguros_paciente_id ON paciente_seguros(paciente_id);
