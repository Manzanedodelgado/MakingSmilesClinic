-- Directorio de proveedores: contacto + clasificación
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS telefono VARCHAR(40);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS direccion VARCHAR(300);
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS forma_pago_defecto VARCHAR(40);
