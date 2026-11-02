-- 29-oct-2026: cuatro reembolsos más a Juan Antonio Manzanedo que el motor creó como "honorarios" con IRPF.
-- Son compras que él pagó y la clínica le devolvió (confirmado por el usuario): sin retención.
--   3048 (apunte 1454, 29-11-2019, 560 €): televisor y mesa
--   3211 (apunte 2437, 26-11-2021, 175,45 €): recibo Vodafone
--   3394 (apunte 3142, 23-02-2023, 1.820 €): pago por tarjeta Neomarketing
--   3580 (apunte 3685, 12-02-2024, 505 €): campañas de Instagram
UPDATE gastos SET retencion = 0, base_imponible = total,
       concepto = 'Reembolso a Juan Antonio Manzanedo: televisor y mesa. Sin retención de IRPF'
 WHERE id = 3048 AND movimiento_id = 1454 AND total = 560.00;
UPDATE gastos SET retencion = 0, base_imponible = total,
       concepto = 'Reembolso a Juan Antonio Manzanedo: recibo Vodafone. Sin retención de IRPF'
 WHERE id = 3211 AND movimiento_id = 2437 AND total = 175.45;
UPDATE gastos SET retencion = 0, base_imponible = total,
       concepto = 'Reembolso a Juan Antonio Manzanedo: pago por tarjeta Neomarketing. Sin retención de IRPF'
 WHERE id = 3394 AND movimiento_id = 3142 AND total = 1820.00;
UPDATE gastos SET retencion = 0, base_imponible = total,
       concepto = 'Reembolso a Juan Antonio Manzanedo: campañas de Instagram. Sin retención de IRPF'
 WHERE id = 3580 AND movimiento_id = 3685 AND total = 505.00;
