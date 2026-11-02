-- 29-oct-2026: pago 27921 (26-05-2023, Elena Llarena Ramos): Pepper financió 1.250 € y se entregaron 1.000 € en
-- efectivo a la paciente por tratamiento no realizado. La paciente firmó el documento de devolución (lo confirma
-- el usuario). Es una salida de efectivo (Debe en metálico) justificada: un gasto 'Devoluciones' pagado en metálico.
INSERT INTO gastos (created_at, updated_at, centro_id, fecha, concepto, base_imponible, iva_pct, total, es_gasto_lab,
                    numero_factura, proveedor_extraido, estado, categoria, forma_pago, tipo_documento, fiable,
                    retencion, suplido, seguridad_social, divisa)
SELECT now(), now(), 1, DATE '2023-05-26',
       'Devolución en efectivo a Elena Llarena Ramos por tratamiento no realizado (financiación Pepper, pago 27921). Documento de devolución firmado por la paciente',
       1000, 0, 1000, false, 'DEV-27921', 'Elena Llarena Ramos', 'pagada', 'Devoluciones', 'Metálico', 'otro',
       true, 0, 0, 0, 'EUR'
 WHERE NOT EXISTS (SELECT 1 FROM gastos WHERE numero_factura = 'DEV-27921');
