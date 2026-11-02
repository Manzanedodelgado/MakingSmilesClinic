-- 075 · Lista de precios Hexa3Dental 2021 · Diseño y fabricación (jmd, 17-oct-2026)
-- Fuente: Uploads/Lista precios Hexa3Dental 2021 Diseño y Fabricacion.pdf. Proveedor 493.
-- "Sobre interface de titanio 10 € más/pieza en todos los materiales" → variante -TI con +10 €.
-- PMMA multicapa = PMMA (30 €) + incremento 5 €. No representables como trabajo fijo:
-- "trabajos de gran volumen (+17 mm) 20 % adicional" y "trabajos especiales: solicitar presupuesto".
BEGIN;
DO $$ BEGIN
    UPDATE proveedores SET es_laboratorio = true, updated_at = now() WHERE id = 493 AND nombre = 'Hexa3Dental S.L.';
    IF NOT FOUND THEN RAISE EXCEPTION '075: proveedor 493 Hexa3Dental no encontrado'; END IF;
END $$;
INSERT INTO laboratorio_trabajos (centro_id, proveedor_id, codigo, nombre, coste)
SELECT p.centro_id, 493, v.codigo, v.nombre, v.coste FROM proveedores p, (VALUES
  ('H3D-EMAX',     'Disilicato de litio IPS e.max CAD',                                   110.00),
  ('H3D-EMAX-TI',  'Disilicato de litio IPS e.max CAD sobre interface de titanio',        120.00),
  ('H3D-ENAMIC',   'Vita ENAMIC',                                                         110.00),
  ('H3D-ENAMIC-TI','Vita ENAMIC sobre interface de titanio',                              120.00),
  ('H3D-ZRMC',     'Zirconio estructura cementada monolítica multicapa',                   95.00),
  ('H3D-ZRMC-TI',  'Zirconio estructura cementada monolítica multicapa sobre interface de titanio', 105.00),
  ('H3D-ZRMO',     'Zirconio estructura cementada monolítica monocromática',               85.00),
  ('H3D-ZRMO-TI',  'Zirconio estructura cementada monolítica monocromática sobre interface de titanio', 95.00),
  ('H3D-PMMA',     'Provisional PMMA estructura cementada corona/póntica',                 30.00),
  ('H3D-PMMA-TI',  'Provisional PMMA estructura cementada corona/póntica sobre interface de titanio', 40.00),
  ('H3D-PMMAMC',   'Provisional PMMA multicapa estructura cementada corona/póntica',       35.00),
  ('H3D-PMMAMC-TI','Provisional PMMA multicapa estructura cementada corona/póntica sobre interface de titanio', 45.00),
  ('H3D-GRAF',     'Grafeno G-CAM estructura cementada corona/póntica',                    80.00),
  ('H3D-GRAF-TI',  'Grafeno G-CAM estructura cementada corona/póntica sobre interface de titanio', 90.00)
) AS v(codigo, nombre, coste) WHERE p.id = 493
ON CONFLICT DO NOTHING;
COMMIT;
