-- 29-oct-2026: tres reembolsos a Juan Antonio Manzanedo que el motor de conciliación creó como "honorarios"
-- (con retención de IRPF del 15 %), pero son compras que él pagó y la clínica le devolvió: NO llevan IRPF.
--   3043 (apunte 1409, 08-11-2019, 4.598 €): Invisalign ("Pago 2 invisa")
--   3111 (apunte 1962, 01-02-2021, 2.405 €): ordenador ("pago de ordenador")
--   3667 (apunte 4417, 02-06-2025, 1.300 €): factura Motor de Implantes
-- El total (lo que salió del banco) no cambia: la base pasa a ser el total y la retención a 0.
UPDATE gastos SET retencion = 0, base_imponible = total,
       concepto = 'Reembolso a Juan Antonio Manzanedo: Invisalign (pago 2 invisa). Sin retención de IRPF'
 WHERE id = 3043 AND movimiento_id = 1409 AND total = 4598.00;
UPDATE gastos SET retencion = 0, base_imponible = total,
       concepto = 'Reembolso a Juan Antonio Manzanedo: ordenador. Sin retención de IRPF'
 WHERE id = 3111 AND movimiento_id = 1962 AND total = 2405.00;
UPDATE gastos SET retencion = 0, base_imponible = total,
       concepto = 'Reembolso a Juan Antonio Manzanedo: factura Motor de Implantes. Sin retención de IRPF'
 WHERE id = 3667 AND movimiento_id = 4417 AND total = 1300.00;
