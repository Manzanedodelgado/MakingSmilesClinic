-- 076 · Varios trabajos de laboratorio por precio de tarifa + interfase y tornillo (jmd, 17-oct-2026)
-- Orden del usuario: añadir los costes de interfase (18 €) y tornillo (4 €). Una corona sobre
-- implante suma corona + interfase + tornillo, así que el precio de tarifa deja de apuntar a UN
-- trabajo (tarifa_precios.laboratorio_trabajo_id, 073) y pasa a una lista con cantidad.
-- Coste de laboratorio de un precio de tarifa = Σ cantidad × laboratorio_trabajos.coste.
-- Interfase y tornillo con Hexa3Dental (493): su factura de 30-jun-2026 incluye "Interfase de titanio IPD".
-- Paso 1 de 2 (solo añade). La columna laboratorio_trabajo_id se quita en 077, tras desplegar.
BEGIN;
CREATE TABLE IF NOT EXISTS tarifa_precio_trabajos (
    id                     serial PRIMARY KEY,
    created_at             timestamp NOT NULL DEFAULT now(),
    updated_at             timestamp NOT NULL DEFAULT now(),
    tarifa_precio_id       integer NOT NULL REFERENCES tarifa_precios(id),
    laboratorio_trabajo_id integer NOT NULL REFERENCES laboratorio_trabajos(id),
    cantidad               numeric(6,2) NOT NULL DEFAULT 1 CHECK (cantidad > 0),
    UNIQUE (tarifa_precio_id, laboratorio_trabajo_id)
);
CREATE INDEX IF NOT EXISTS ix_tarifa_precio_trabajos_trabajo ON tarifa_precio_trabajos (laboratorio_trabajo_id);
COMMENT ON TABLE tarifa_precio_trabajos IS 'Trabajos de laboratorio de cada precio de tarifa; coste de laboratorio = Σ cantidad × coste.';

INSERT INTO tarifa_precio_trabajos (tarifa_precio_id, laboratorio_trabajo_id)
SELECT id, laboratorio_trabajo_id FROM tarifa_precios WHERE laboratorio_trabajo_id IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO laboratorio_trabajos (centro_id, proveedor_id, codigo, nombre, coste)
SELECT p.centro_id, 493, v.codigo, v.nombre, v.coste FROM proveedores p, (VALUES
  ('H3D-INTERFASE', 'Interfase de titanio', 18.00),
  ('H3D-TORNILLO',  'Tornillo',              4.00)
) AS v(codigo, nombre, coste) WHERE p.id = 493
ON CONFLICT DO NOTHING;
COMMIT;
