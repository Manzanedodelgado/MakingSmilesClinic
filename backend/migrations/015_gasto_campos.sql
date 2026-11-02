-- Rediseño definitivo del pipeline de facturas: campos nuevos del documento.
-- Se extraen y guardan tal como vienen (sin inventar): divisa, tipo de documento,
-- retención IRPF, forma de pago. (categoria ya existía.)

ALTER TABLE gastos ADD COLUMN IF NOT EXISTS retencion NUMERIC(10,2) NOT NULL DEFAULT 0;
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS divisa VARCHAR(3) DEFAULT 'EUR';
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(20);
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS forma_pago VARCHAR(40);
