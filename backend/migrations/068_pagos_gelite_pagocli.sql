-- 068 · Cargar en pagos los pagos de GELITE (PagoCli) salvo los negativos (jmd, 17-oct-2026)
-- Órdenes del usuario:
--   · Nueva forma de pago "Regularización Master Dental" (para los 14 de Mutua, que son abonos
--     "para regularizar saldo" de junio-julio 2019).
--   · Talón de dic-2025 / feb-2026 (5) → Efectivo. Domiciliación (2) → Efectivo.
--   · Los 250 pagos NEGATIVOS se dejan fuera de momento (incluye los 14 de Mutua).
-- Paciente: el de su tratamiento en GELITE (TtosMed.IdPac por IdentTM); los 48 sin tratamiento,
-- el único paciente de su titular en la app. Procedencia: GELITE:PagoCli + IdPagoCli.
BEGIN;
INSERT INTO formas_pago (created_at, updated_at, id, codigo, nombre, grupo, en_caja, activo, orden)
VALUES (now(), now(), 17, NULL, 'Regularización Master Dental', 'Otros', false, true, 230)
ON CONFLICT (id) DO NOTHING;

CREATE TEMP TABLE _g (paciente_id int, cliente_id int, fecha date, importe numeric, forma int,
                      anulado boolean, automatico boolean, num_recibo text, num_factura text,
                      num_transaccion text, id_pagocli int) ON COMMIT DROP;
\copy _g FROM '/tmp/pagocli.tsv' WITH (FORMAT text, NULL '\N')

INSERT INTO pagos (created_at, updated_at, centro_id, cliente_id, paciente_id, fecha, importe,
                   forma_pago_id, automatico, anulado, liquidado, num_recibo, num_factura,
                   num_transaccion, origen, origen_id_gelite, origen_fecha)
SELECT now(), now(), 1, cliente_id, paciente_id, fecha, importe, forma, automatico, anulado, false,
       num_recibo, num_factura, num_transaccion, 'GELITE:PagoCli', id_pagocli::text, DATE '2026-10-15'
  FROM _g WHERE importe >= 0;

INSERT INTO gelite_equivalencias (entidad, id_gelite, nombre_gelite, id_app, nombre_app, estado, filas_usando, revisado, nota)
SELECT 'pagos', origen_id_gelite::int, 'GELITE:PagoCli', id,
       'pago ' || id || ' · paciente ' || paciente_id || ' · ' || fecha || ' · ' || importe || ' €',
       'DISTINTO', 1, true, 'Pago migrado de PagoCli (id_gelite = IdPagoCli).'
  FROM pagos WHERE origen = 'GELITE:PagoCli';

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM pagos WHERE origen = 'GELITE:PagoCli';
    IF n <> 13698 THEN RAISE EXCEPTION '068: % pagos de PagoCli, se esperaban 13.698', n; END IF;
    SELECT count(*) INTO n FROM pagos WHERE origen = 'GELITE:PagoCli' AND importe < 0;
    IF n > 0 THEN RAISE EXCEPTION '068: han entrado % negativos', n; END IF;
END $$;
COMMIT;
