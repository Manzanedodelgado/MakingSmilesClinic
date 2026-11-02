-- Liquidación de TPV que abonó cada cobro con tarjeta (conciliación tarjeta ↔ pagos).
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS liquidacion_mov_id INTEGER REFERENCES movimientos_bancarios(id);
CREATE INDEX IF NOT EXISTS ix_pagos_liquidacion_mov_id ON pagos(liquidacion_mov_id);
