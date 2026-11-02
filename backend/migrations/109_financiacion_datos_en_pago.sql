-- 29-oct-2026: los datos de la financiación vienen en el texto libre de la fila "Pago a cuenta de Tratamientos" del
-- historial del paciente en Gelite (TtosMed.Notas, enlazada por PagoCli.IdentTM = TtosMed.Ident). Se pasan a la línea
-- del pago: financiera, nº de meses, cuota mensual (si la dice el texto), % descontado por la financiera
-- ((importe - neto) / importe) y el texto original en `motivo`. Solo se rellena lo que está vacío.
-- La entrada no consta en los textos: se deja sin rellenar.
INSERT INTO financieras (centro_id, nombre, comision_pct, activo)
SELECT 1, 'Santander Consumer', 0, true WHERE NOT EXISTS (SELECT 1 FROM financieras WHERE nombre = 'Santander Consumer');
INSERT INTO financieras (centro_id, nombre, comision_pct, activo)
SELECT 1, 'Openbank', 0, true WHERE NOT EXISTS (SELECT 1 FROM financieras WHERE nombre = 'Openbank');

WITH g(gelite_id, fin, meses, cuota, texto) AS (VALUES
(6259,'P',NULL,NULL,'PEPPER'),
(6260,'P',NULL,NULL,'PEPPPER'),
(6258,'P',NULL,NULL,'PEPPER'),
(6360,'P',NULL,NULL,'pEPPER'),
(6426,'P',NULL,NULL,'PEPPER'),
(6430,'S',NULL,NULL,'santander'),
(6530,'P',NULL,NULL,'PEPPER'),
(6720,'P',36,NULL,'PEPPER 36MESES'),
(6730,'P',24,NULL,'Pepper 24 meses'),
(6867,'P',12,NULL,'pepper 12 meses'),
(6802,'P',36,NULL,'PEPPER 36MESES'),
(7047,'S',48,NULL,'Santandes Consumer 48 meses sin intereses'),
(7335,'P',36,NULL,'Pepper 36 meses'),
(7347,'P',12,NULL,'PEPPER 12 MESES'),
(7417,'S',48,NULL,'SANTANDER 48 MESES'),
(7423,'S',48,NULL,'santander 48 meses'),
(7503,'S',48,NULL,'SANTANDER CONSUMER 48 MESES SIN INTERESES'),
(7557,'S',24,NULL,'SANTANDER 24 MESES'),
(7555,'P',18,NULL,'PEPPER 18 MESES'),
(7556,'P',24,NULL,'pEPPER 24 MESES'),
(7669,'P',12,NULL,'PEPPER 12 MESES'),
(7671,'P',18,NULL,'PPEPER 18 MESES'),
(7709,'S',48,NULL,'santander 48 meses'),
(8145,NULL,NULL,NULL,'SALDO TRASPASADO POR SERGIO FERNANDEZ HERNANDEZ CON AUTORIZACION DE AMBOS'),
(8147,'S',48,NULL,'SANTANDER 48 MESES'),
(8258,'S',48,NULL,'SANTANDER 48 MESES'),
(8396,'S',36,NULL,'SANTANDER 36 MESES'),
(8468,'S',48,NULL,'santander 48 meses'),
(8640,'P',12,NULL,'PEPPER 12 MESES'),
(8650,'S',24,NULL,'SANTANDER 24 MESES'),
(8663,'S',24,NULL,'santander 24 meses'),
(8706,'P',36,NULL,'PEPPER 36 MESES'),
(8709,'P',12,NULL,'Pepper 12 meses'),
(8718,'P',12,NULL,'pepper express 12 meses'),
(8743,'S',48,NULL,'santander 48 meses'),
(8774,'P',36,NULL,'Pepper  36 meses'),
(8888,'S',24,NULL,'SANTANDEWR 24 MESES'),
(8936,'S',12,NULL,'santander 12 meses'),
(8991,'S',24,NULL,'santnander 24 meses'),
(9047,'P',12,NULL,'PEPPER EXPRESS 12 MESES'),
(9088,'P',15,NULL,'PEPPER EXPRESS 15 MESES'),
(9333,'P',36,NULL,'PEPPER 36 MESES'),
(9194,'P',12,NULL,'PEPPER 12 MESES'),
(9199,'P',24,NULL,'PAGO REALIZADO POR FINANCIERA PEPPER A 24 MESES. CUOTA MENSUAL 87.50'),
(9200,'P',18,NULL,'PEPPER 18 MESES'),
(9536,'S',48,NULL,'SANTANDER 48 MESES'),
(9492,'P',12,NULL,'ppper 12 meses'),
(9600,'P',6,NULL,'PEPPER EXPRESS A 6 MESES'),
(9809,'P',12,NULL,'12 meses pepper'),
(9731,'P',24,NULL,'PEPPER 24M MESES'),
(9990,'P',30,NULL,'PPER 30 MESES'),
(10033,'P',12,NULL,'pepper 12 meses'),
(10051,'S',12,NULL,'SANTANDER 12 MESES'),
(10147,'P',36,NULL,'Pepper 36 meses'),
(10176,'P',9,NULL,'pepper 9 meses'),
(10410,'P',NULL,NULL,'pepper'),
(10551,'S',48,NULL,'SANTANDER 48 MESES'),
(10572,'S',12,NULL,'santnader 12 meses'),
(10597,'S',48,NULL,'SANTANDER 48 MESES A NOMBRE DE PEDRO ABRIL'),
(10624,'P',12,NULL,'PEPPER EXPRESS 12 MESES'),
(10832,'S',48,NULL,'Santander 48 meses s/i'),
(10861,'P',12,NULL,'PEPPER EXPRESS 12 MESES'),
(10941,'P',NULL,NULL,'pepper. se financian 1250 y se entregan 1000 al paciente por tratamiento no realizado'),
(11217,'S',48,NULL,'santander 48 meses'),
(11107,'S',48,NULL,'santander 48 meses'),
(11218,'P',9,NULL,'PEPPER 9 MESES'),
(11222,'S',48,NULL,'santander 48 meses'),
(11313,'S',18,NULL,'SANTANDER 18 MESES'),
(11316,'S',36,NULL,'SANTANDER 36 MESES'),
(11358,'S',24,NULL,'santnandes 24'),
(11456,'S',18,NULL,'santander 18 meses'),
(11637,'P',12,NULL,'pepper express 12 meses'),
(11680,'S',48,NULL,'SANTANDER 48 MESES'),
(11735,'P',9,NULL,'peper a 9 meses'),
(11774,NULL,9,37.69,'9 MESES EXPRESS . COUTA MENSUAL 37.69'),
(11836,'P',9,NULL,'PEPPER 9 MESES 138...EUROS'),
(11853,'S',12,NULL,'santander 12 meses'),
(12133,'S',24,NULL,'SANTANDER 24 MESES'),
(12249,'S',24,NULL,'SANTANDER 24 MESES'),
(12218,'S',12,NULL,'SANTANDER 12 MESES'),
(12546,'P',18,NULL,'peper express 18 meses'),
(12658,'P',24,NULL,'PEPPER 24 MESES'),
(12657,'P',36,NULL,'PEPPER 36 MESES'),
(12749,'S',36,NULL,'SANTANDER 36 MESES'),
(13165,NULL,NULL,NULL,NULL),
(12930,'S',48,NULL,'SANTANDER 48 MESES 02/02/2025'),
(13426,'S',24,NULL,'SANTANDER 24 MESES'),
(13173,'P',24,NULL,'Pepper 24 meses'),
(13212,'P',NULL,NULL,'ff PEPPER EXPRESS'),
(13347,'P',20,104,'PPEPER 20 MESES 104 AL MES'),
(13402,'S',24,NULL,'SANTANDER 24 MESES'),
(13380,'S',36,NULL,'SANTNADER 36 MESES'),
(13379,'S',36,NULL,'SANTANDER 36 MESES'),
(13381,'S',48,NULL,'SANTANDER 48 MESES'),
(13386,'P',NULL,NULL,'pepper'),
(13388,'P',NULL,NULL,'pepper a nombre de su cuñado'),
(13387,'P',NULL,NULL,'pepper a nombre de su marido'),
(13389,'S',24,NULL,'santander 24m'),
(13550,NULL,NULL,NULL,NULL),
(13614,'S',36,NULL,'SANTANDER 36 MESES COMIENZA 01/10/25')
)
UPDATE pagos p SET
  financiera_id = COALESCE(p.financiera_id, CASE g.fin WHEN 'S' THEN (SELECT id FROM financieras WHERE nombre='Santander Consumer')
                                                         WHEN 'P' THEN (SELECT id FROM financieras WHERE nombre='Pepper') END),
  num_cuotas    = COALESCE(p.num_cuotas, g.meses),
  cuota_mensual = COALESCE(p.cuota_mensual, g.cuota),
  motivo        = COALESCE(NULLIF(p.motivo, ''), g.texto)
FROM g WHERE p.origen = 'GELITE:PagoCli' AND p.origen_id_gelite = g.gelite_id::text AND NOT p.anulado;

-- Sin texto: la financiera se deduce de la transferencia que liquida el pago.
UPDATE pagos p SET financiera_id = CASE
    WHEN m.concepto_banco ILIKE '%santander%' THEN (SELECT id FROM financieras WHERE nombre='Santander Consumer')
    WHEN m.concepto_banco ILIKE '%pepper%'    THEN (SELECT id FROM financieras WHERE nombre='Pepper')
    WHEN m.concepto_banco ILIKE '%openbank%'  THEN (SELECT id FROM financieras WHERE nombre='Openbank') END
  FROM movimientos_bancarios m, formas_pago f
 WHERE m.id = p.liquidacion_mov_id AND f.id = p.forma_pago_id AND f.grupo = 'Financiación'
   AND NOT p.anulado AND p.financiera_id IS NULL;

-- % que la financiera se queda (intereses): (100 % pagado por el paciente - neto ingresado) / importe.
UPDATE pagos p SET interes_pct = round(100 * (p.importe - p.neto) / p.importe, 2)
  FROM formas_pago f
 WHERE f.id = p.forma_pago_id AND f.grupo = 'Financiación' AND NOT p.anulado
   AND p.neto IS NOT NULL AND p.importe > 0 AND p.interes_pct IS NULL;
