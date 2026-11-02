-- Bloque A del rediseño: la factura es autosuficiente (guarda los datos fiscales del emisor)
-- y las asociaciones banco↔factura/pago son 1:1 reales.

ALTER TABLE gastos ADD COLUMN IF NOT EXISTS cif_emisor VARCHAR(20);
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS emisor_datos TEXT;
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS incidencias TEXT;
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS fiable BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS ix_gastos_cif_emisor ON gastos(cif_emisor);
CREATE INDEX IF NOT EXISTS ix_gastos_fiable ON gastos(fiable);

-- 1:1 reales: un apunte bancario se asocia a una sola factura/pago/documento.
CREATE UNIQUE INDEX IF NOT EXISTS uq_mov_gasto ON movimientos_bancarios(gasto_id) WHERE gasto_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mov_pago ON movimientos_bancarios(pago_id) WHERE pago_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mov_docadmin ON movimientos_bancarios(documento_admin_id) WHERE documento_admin_id IS NOT NULL;
