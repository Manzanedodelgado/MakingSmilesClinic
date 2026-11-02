-- 29-oct-2026: toda transferencia de financiera tiene pago de paciente (usuario). Se acoplan a transferencias de
-- financiera sin pago los pagos que se anotaron con otra forma de pago y se corrige la forma a Financiación.
-- Criterio: la transferencia llega entre -10 y +8 días del pago (mediana 1 día en los 95 pares ya enlazados) y el
-- importe ingresado es el bruto menos el descuento de la financiera.
--   25492 (Cristina Sánchez Díez, 07-07-2021, 9.175 €): era 'Transferencia'; Gelite dice Santander. Apunte 2211.
--   27915 (Benita Posado Jañez, 25-05-2023, 1.320 €): era 'Efectivo'; apunte 3288 (Pepper, 29-05-2023, 1.171,25 €).
--   30225 (Antonio Baena Navarro, 09-04-2025, 1.220 €): era 'Efectivo'; apunte 4340 (Pepper, 10-04-2025, 1.197,60 €).
UPDATE pagos p SET forma_pago_id = (SELECT id FROM formas_pago WHERE grupo = 'Financiación' AND nombre = 'Financiación'),
       liquidacion_mov_id = v.mov, neto = v.neto,
       financiera_id = (SELECT id FROM financieras WHERE nombre = v.fin),
       interes_pct = round(100 * (p.importe - v.neto) / p.importe, 2), liquidado = true,
       motivo = COALESCE(NULLIF(p.motivo, '') || ' · ', '') || 'Reclasificado de ' || v.antes || ' a financiación (apunte ' || v.mov || ')'
  FROM (VALUES (25492, 2211, 7982.25, 'Santander Consumer', 'transferencia'),
               (27915, 3288, 1171.25, 'Pepper', 'efectivo'),
               (30225, 4340, 1197.60, 'Pepper', 'efectivo')) AS v(pid, mov, neto, fin, antes)
 WHERE p.id = v.pid AND NOT p.anulado;
