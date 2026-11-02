-- Dto. realizado que puede aplicar (o no) al doctor en su liquidación.
-- Producción → Tratamientos: columna "Dto. realizado" (descuento ya existía) + check "aplica al doctor".
ALTER TABLE tratamientos_realizados
  ADD COLUMN IF NOT EXISTS descuento_aplica_doctor BOOLEAN NOT NULL DEFAULT false;
