-- 016 · Gasto: columna SUPLIDO (gasto exento de IVA que el proveedor adelanta por cuenta del cliente).
-- Ecuación de la factura con suplido:  total = base + round(base*iva_pct/100) − retención + suplido
-- El suplido NO forma parte de la base imponible ni lleva IVA (art. 78.Tres.3 LIVA): va aparte.
-- Caso real que motivó la columna: SRCL Consenur (CIF B86208824) — "Suplido Previlabor/Prevención".
--
-- Reversible:  ALTER TABLE gastos DROP COLUMN IF EXISTS suplido;

ALTER TABLE gastos ADD COLUMN IF NOT EXISTS suplido NUMERIC(10,2) NOT NULL DEFAULT 0;
