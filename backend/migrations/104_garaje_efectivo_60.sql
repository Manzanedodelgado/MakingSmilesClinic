-- 29-oct-2026: el garaje en efectivo son 60 € al mes, no 65 (indicado por el usuario).
-- Solo las 88 filas 'Garaje (efectivo)' (estimadas, sin factura, sin apunte): total y base pasan de 65 a 60.
UPDATE gastos SET total = 60.00, base_imponible = 60.00
 WHERE proveedor_extraido = 'Garaje (efectivo)' AND total = 65.00 AND movimiento_id IS NULL;
