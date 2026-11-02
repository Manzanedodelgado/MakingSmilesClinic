-- 073 · Lista de precios de laboratorio (jmd, 17-oct-2026)
-- Orden del usuario: el coste de laboratorio no vive en el catálogo de tratamientos ni como importe
-- suelto en la tarifa, porque varía según el laboratorio. Cada laboratorio (proveedores con
-- es_laboratorio) tiene su lista de trabajos con su coste; cada precio de tarifa indica el id del
-- trabajo de laboratorio que le corresponde y el coste se lee de ahí.
-- Paso 1 de 2 (solo añade). Las columnas antiguas se quitan en 074, tras desplegar el código.
BEGIN;
CREATE TABLE IF NOT EXISTS laboratorio_trabajos (
    id            serial PRIMARY KEY,
    created_at    timestamp NOT NULL DEFAULT now(),
    updated_at    timestamp NOT NULL DEFAULT now(),
    centro_id     integer NOT NULL REFERENCES centros(id),
    proveedor_id  integer NOT NULL REFERENCES proveedores(id),
    codigo        varchar(40),
    nombre        varchar(200) NOT NULL,
    coste         numeric(10,2) NOT NULL CHECK (coste >= 0),
    activo        boolean NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS ix_laboratorio_trabajos_centro_id ON laboratorio_trabajos (centro_id);
CREATE INDEX IF NOT EXISTS ix_laboratorio_trabajos_proveedor_id ON laboratorio_trabajos (proveedor_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_laboratorio_trabajos_proveedor_codigo
    ON laboratorio_trabajos (proveedor_id, codigo) WHERE codigo IS NOT NULL;
COMMENT ON TABLE laboratorio_trabajos IS 'Lista de precios de cada laboratorio (proveedores.es_laboratorio): un trabajo y su coste.';

ALTER TABLE tarifa_precios
    ADD COLUMN IF NOT EXISTS laboratorio_trabajo_id integer REFERENCES laboratorio_trabajos(id);
CREATE INDEX IF NOT EXISTS ix_tarifa_precios_laboratorio_trabajo_id ON tarifa_precios (laboratorio_trabajo_id);
COMMENT ON COLUMN tarifa_precios.laboratorio_trabajo_id IS 'Trabajo de laboratorio de este tratamiento en esta tarifa; su coste es el coste de laboratorio.';
COMMIT;
