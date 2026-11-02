-- Asociación apunte bancario (HABER) ↔ pago de paciente
ALTER TABLE movimientos_bancarios ADD COLUMN IF NOT EXISTS pago_id INTEGER REFERENCES pagos(id);
CREATE INDEX IF NOT EXISTS ix_mov_pago ON movimientos_bancarios(pago_id);
