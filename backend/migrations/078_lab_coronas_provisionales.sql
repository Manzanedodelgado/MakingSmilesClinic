-- 078 · Coste de laboratorio de las coronas provisionales (jmd, 17-oct-2026)
-- Orden del usuario: diferenciar las provisionales SOBRE IMPLANTE, que suman interfase y tornillo.
--   Sobre implante (563, 621): PMMA sobre interface de titanio + interfase + tornillo = 40+18+4 = 62 €
--   Sobre diente, de laboratorio (565): PMMA = 30 €
-- Las de clínica (620, 507, carilla 616) no llevan coste de laboratorio. Solo tratamientos activos.
BEGIN;
INSERT INTO tarifa_precio_trabajos (tarifa_precio_id, laboratorio_trabajo_id, cantidad)
SELECT tp.id, lt.id, 1
FROM tarifa_precios tp
JOIN (VALUES (563,'H3D-PMMA-TI'),(563,'H3D-INTERFASE'),(563,'H3D-TORNILLO'),
             (621,'H3D-PMMA-TI'),(621,'H3D-INTERFASE'),(621,'H3D-TORNILLO'),
             (565,'H3D-PMMA')) AS v(tto, codigo) ON v.tto = tp.tratamiento_id
JOIN laboratorio_trabajos lt ON lt.codigo = v.codigo AND lt.proveedor_id = 493
ON CONFLICT DO NOTHING;
DO $$ DECLARE n int; BEGIN
    SELECT count(*) INTO n FROM tarifa_precio_trabajos;
    IF n <> 7 THEN RAISE EXCEPTION '078: esperaba 7 enlaces y hay %', n; END IF;
END $$;
COMMIT;
