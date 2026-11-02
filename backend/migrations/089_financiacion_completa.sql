-- 089: Campos completos de financiación en pagos
-- Permite registrar: financiera, entrada, cuotas, interés, y separar importe paciente vs neto clínica

-- Catálogo de entidades financieras (Cetelem, Pepper, Sabadell Consumer, etc.)
CREATE TABLE IF NOT EXISTS financieras (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    centro_id INTEGER NOT NULL REFERENCES centros(id),
    nombre VARCHAR(120) NOT NULL,
    comision_pct NUMERIC(5,2) NOT NULL DEFAULT 0,  -- comisión estándar (%)
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
-- Arreglar defaults si la tabla existía sin ellos
ALTER TABLE financieras ALTER COLUMN created_at SET DEFAULT NOW();
ALTER TABLE financieras ALTER COLUMN updated_at SET DEFAULT NOW();
ALTER TABLE financieras ALTER COLUMN activo SET DEFAULT TRUE;
ALTER TABLE financieras ALTER COLUMN comision_pct SET DEFAULT 0;
CREATE INDEX IF NOT EXISTS ix_financieras_centro ON financieras(centro_id);

-- Campos de financiación en pagos
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS financiera_id INTEGER REFERENCES financieras(id);
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS entrada NUMERIC(12,2);          -- importe de entrada (si hay)
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS num_cuotas INTEGER;             -- nº de cuotas
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS interes_pct NUMERIC(5,2);       -- % interés aplicado
ALTER TABLE pagos ADD COLUMN IF NOT EXISTS cuota_mensual NUMERIC(12,2);    -- importe de cada cuota

CREATE INDEX IF NOT EXISTS ix_pagos_financiera ON pagos(financiera_id);

-- Insertar financieras comunes (centro 1)
INSERT INTO financieras (centro_id, nombre, comision_pct) VALUES
    (1, 'Cetelem', 5.00),
    (1, 'Pepper', 4.50),
    (1, 'Sabadell Consumer', 5.50),
    (1, 'Cofidis', 6.00)
ON CONFLICT DO NOTHING;

COMMENT ON COLUMN pagos.importe IS 'Bruto: 100% que abona/financia el PACIENTE (lo que refleja su plan económico)';
COMMENT ON COLUMN pagos.neto IS 'Lo que RECIBE la clínica tras descontar comisión de financiera (para facturación/contabilidad)';
COMMENT ON COLUMN pagos.financiera_id IS 'Entidad financiera que gestiona la financiación';
COMMENT ON COLUMN pagos.entrada IS 'Importe de entrada (pago inicial antes de cuotas)';
COMMENT ON COLUMN pagos.num_cuotas IS 'Número de cuotas de la financiación';
COMMENT ON COLUMN pagos.interes_pct IS 'Porcentaje de interés aplicado al paciente';
COMMENT ON COLUMN pagos.cuota_mensual IS 'Importe de cada cuota mensual';
