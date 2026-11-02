-- 006 · Gestoría: tablas/columnas para el modo Facturación (gastos, banco, fiscal).
-- La Producción (doctores/pacientes/tratamientos) sale de tablas ya existentes.

ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS email_contacto    VARCHAR(255);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS iban              VARCHAR(34);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS categoria_defecto VARCHAR(80);

ALTER TABLE gastos ADD COLUMN IF NOT EXISTS numero_factura     VARCHAR(60);
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS proveedor_extraido VARCHAR(200);
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS archivo_pdf_url    VARCHAR(500);
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS estado             VARCHAR(40) NOT NULL DEFAULT 'pendiente';
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS categoria          VARCHAR(40);
ALTER TABLE gastos ADD COLUMN IF NOT EXISTS gmail_message_id   VARCHAR(120);
CREATE UNIQUE INDEX IF NOT EXISTS uq_gastos_gmail_msg
    ON gastos (gmail_message_id) WHERE gmail_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS movimientos_bancarios (
  id                 SERIAL PRIMARY KEY,
  created_at         TIMESTAMP WITHOUT TIME ZONE,
  updated_at         TIMESTAMP WITHOUT TIME ZONE,
  centro_id          INTEGER NOT NULL REFERENCES centros(id),
  iban_cuenta        VARCHAR(34)   NOT NULL,
  fecha_operacion    DATE          NOT NULL,
  concepto_banco     VARCHAR(300)  NOT NULL,
  importe            NUMERIC(12,2) NOT NULL,
  saldo_posterior    NUMERIC(12,2),
  categoria          VARCHAR(40),
  estado_concil      VARCHAR(20)   NOT NULL DEFAULT 'abierto',
  gasto_id           INTEGER REFERENCES gastos(id),
  documento_admin_id INTEGER REFERENCES documentos_admin(id),
  CONSTRAINT uq_mov_banc UNIQUE (iban_cuenta, fecha_operacion, concepto_banco, importe)
);
CREATE INDEX IF NOT EXISTS ix_mov_banc_centro ON movimientos_bancarios (centro_id);
CREATE INDEX IF NOT EXISTS ix_mov_banc_fecha  ON movimientos_bancarios (fecha_operacion);

CREATE TABLE IF NOT EXISTS modelos_fiscales (
  id               SERIAL PRIMARY KEY,
  created_at       TIMESTAMP WITHOUT TIME ZONE,
  updated_at       TIMESTAMP WITHOUT TIME ZONE,
  centro_id        INTEGER NOT NULL REFERENCES centros(id),
  modelo           VARCHAR(10)  NOT NULL,
  ejercicio        INTEGER      NOT NULL,
  periodo          VARCHAR(4)   NOT NULL,
  estado           VARCHAR(20)  NOT NULL DEFAULT 'borrador',
  fecha_limite     DATE,
  cuota_resultante NUMERIC(12,2),
  archivo_justif   VARCHAR(500),
  CONSTRAINT uq_modelo_fiscal UNIQUE (centro_id, modelo, ejercicio, periodo)
);
CREATE INDEX IF NOT EXISTS ix_modelo_fiscal_centro ON modelos_fiscales (centro_id);
