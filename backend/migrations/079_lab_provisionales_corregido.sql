-- 079 · Corrige 078 según jmd (17-oct-2026):
--   provisional = 30 € (PMMA); sobre implante se suman 22 € (interfase 18 + tornillo 4) = 52 €;
--   la inmediata sobre implante lleva 5 € de recargo = 57 €. No se usa PMMA sobre interface de titanio.
BEGIN;
INSERT INTO laboratorio_trabajos (centro_id, proveedor_id, codigo, nombre, coste)
SELECT centro_id, 493, 'H3D-REC-INMEDIATA', 'Recargo provisional inmediata sobre implante', 5.00
FROM proveedores WHERE id = 493
ON CONFLICT DO NOTHING;

DELETE FROM tarifa_precio_trabajos x USING tarifa_precios tp
 WHERE tp.id = x.tarifa_precio_id AND tp.tratamiento_id IN (563, 565, 621);

INSERT INTO tarifa_precio_trabajos (tarifa_precio_id, laboratorio_trabajo_id, cantidad)
SELECT tp.id, lt.id, 1
FROM tarifa_precios tp
JOIN (VALUES (563,'H3D-PMMA'),(563,'H3D-INTERFASE'),(563,'H3D-TORNILLO'),(563,'H3D-REC-INMEDIATA'),
             (621,'H3D-PMMA'),(621,'H3D-INTERFASE'),(621,'H3D-TORNILLO'),
             (565,'H3D-PMMA')) AS v(tto, codigo) ON v.tto = tp.tratamiento_id
JOIN laboratorio_trabajos lt ON lt.codigo = v.codigo AND lt.proveedor_id = 493;

DO $$ DECLARE a numeric; b numeric; c numeric; BEGIN
    SELECT sum(x.cantidad*lt.coste) FILTER (WHERE tp.tratamiento_id=563),
           sum(x.cantidad*lt.coste) FILTER (WHERE tp.tratamiento_id=621),
           sum(x.cantidad*lt.coste) FILTER (WHERE tp.tratamiento_id=565)
      INTO a, b, c
      FROM tarifa_precio_trabajos x JOIN tarifa_precios tp ON tp.id=x.tarifa_precio_id
      JOIN laboratorio_trabajos lt ON lt.id=x.laboratorio_trabajo_id;
    IF a <> 57 OR b <> 52 OR c <> 30 THEN RAISE EXCEPTION '079: costes % / % / % (esperado 57/52/30)', a, b, c; END IF;
END $$;
COMMIT;
