-- Pago financiado: importe = BRUTO (100% que factura/paga el paciente);
-- neto = lo que realmente recibe la clínica. Coste financiero = importe - neto (solo Financiación).
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS neto NUMERIC(12,2);
