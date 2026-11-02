-- 007 · Colaborador: % de IRPF y % de gastos (lab) configurables, para que la
-- liquidación sea idéntica a la .37 (antes eran solo checkboxes on/off).
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS irpf_pct   NUMERIC(5,2);
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS tpc_gastos NUMERIC(5,2);
-- Backfill desde los booleanos existentes (IRPF 15% si estaba marcado; gastos 100% si descontaba lab).
UPDATE colaboradores SET irpf_pct   = 15  WHERE irpf_pct   IS NULL AND aplica_irpf = true;
UPDATE colaboradores SET tpc_gastos = 100 WHERE tpc_gastos IS NULL AND aplica_laboratorio = true;
