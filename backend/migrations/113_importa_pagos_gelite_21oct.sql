-- 30-oct-2026: pagos de GELITE (PagoCli, copia del 21-oct-2026) que faltaban en Making. Orden del usuario: "importalo".
--   · 10 devoluciones (importe negativo, ago-2019 en adelante) con la forma de pago que tienen en Gelite
--   · 10 pagos del 14 al 21-oct-2026 (el 14426, 20 €, queda fuera: su paciente 7025 aún no existe en Making)
-- Paciente = TtosMed.IdPac del tratamiento; cliente = IdCli. Procedencia GELITE:PagoCli + IdPagoCli.
INSERT INTO pagos (created_at, updated_at, centro_id, cliente_id, paciente_id, fecha, importe,
                   forma_pago_id, automatico, anulado, liquidado, num_recibo, origen, origen_id_gelite, origen_fecha)
SELECT now(), now(), 1, v.cli, v.pac, v.fecha::date, v.importe, v.forma, false, false, false, v.recibo,
       'GELITE:PagoCli', v.id::text, DATE '2026-10-30'
  FROM (VALUES
    (6510 , 1350, 1568, '2019-12-13', -98.02 , 2, NULL),
    (6729 , 2918, 3399, '2020-02-21', -250.00, 7, NULL),
    (6915 , 4140, 4812, '2020-06-04', -60.00 , 2, NULL),
    (7219 , 4293, 4965, '2020-08-26', -60.00 , 2, NULL),
    (7357 , 2347, 2733, '2020-10-07', -300.00, 2, NULL),
    (7374 , 2582, 3012, '2020-09-07', -10.00 , 2, NULL),
    (7487 , 2479, 2885, '2020-11-16', -100.00, 6, NULL),
    (7902 , 4159, 4831, '2021-02-24', -1400.00, 2, NULL),
    (8355 , 4657, 5329, '2021-06-16', -140.00, 2, '(R) 50/21'),
    (14384, 5539, 6205, '2026-09-22', -120.00, 2, '(R)9/26'),
    (14417, 6626, 6855, '2026-10-14', 100.00 , 2, NULL),
    (14418, 1465, 1706, '2026-10-14', 200.00 , 6, NULL),
    (14419, 1465, 1706, '2026-10-14', 400.00 , 6, NULL),
    (14420, 6742, 6995, '2026-10-20', 150.00 , 6, NULL),
    (14421, 6744, 6997, '2026-10-20', 140.00 , 6, NULL),
    (14422, 6739, 6992, '2026-10-20', 200.00 , 2, NULL),
    (14423, 6061, 6738, '2026-10-20', 100.00 , 6, NULL),
    (14424, 6674, 6927, '2026-10-20', 600.00 , 2, NULL),
    (14425, 4758, 5430, '2026-10-20', 350.00 , 2, '(R)11/26'),
    (14427, 5458, 6124, '2026-10-21', 800.00 , 6, NULL)
  ) AS v(id, cli, pac, fecha, importe, forma, recibo)
 WHERE NOT EXISTS (SELECT 1 FROM pagos p WHERE p.origen = 'GELITE:PagoCli' AND p.origen_id_gelite = v.id::text);

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos WHERE origen = 'GELITE:PagoCli' AND created_at::date = CURRENT_DATE AND origen_fecha = DATE '2026-10-30';
    IF n <> 20 THEN RAISE EXCEPTION '113: % pagos importados, se esperaban 20', n; END IF;
END $$;
