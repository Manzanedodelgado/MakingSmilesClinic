-- 040 · Tabla maestra de formas de pago de PACIENTES (jmd, 17-oct-2026)
-- Antes había seis listas escritas a mano que no coincidían (Caja, Plan económico, cobro de
-- Inicio, Gestoría, y el texto crudo de Gesden "C Tarjeta de Crédito"…): un mismo cobro con
-- tarjeta quedaba como "Tarjeta" o "C Tarjeta de Crédito" según desde dónde se hiciera.
-- Ahora: una sola tabla. ids 1-15 = TForPago de Gesden (mismo número), 16 = Bizum (lo cobra Inicio).
-- `grupo` sustituye a la agrupación por texto de Gestoría (FORMAS_PAGO_CANON).
-- `en_caja` = se ofrece al cobrar desde la app.
-- Fase 1 de 2: añade pagos.forma_pago_id y lo rellena; la columna de texto pagos.forma_pago
-- se elimina en 041, DESPUÉS de desplegar el backend que ya no la usa. Idempotente.
BEGIN;

CREATE TABLE IF NOT EXISTS formas_pago (
    created_at  timestamp    NOT NULL DEFAULT now(),
    updated_at  timestamp    NOT NULL DEFAULT now(),
    id          integer      PRIMARY KEY,
    codigo      varchar(2),
    nombre      varchar(60)  NOT NULL UNIQUE,
    grupo       varchar(30)  NOT NULL,
    en_caja     boolean      NOT NULL DEFAULT false,
    activo      boolean      NOT NULL DEFAULT true,
    orden       integer      NOT NULL DEFAULT 100
);

INSERT INTO formas_pago (id, codigo, nombre, grupo, en_caja, orden) VALUES
    ( 1, 'D', 'Domiciliación',          'Domiciliación', true,  50),
    ( 2, 'E', 'Efectivo',               'Efectivo',      true,  10),
    ( 3, 'L', 'Letras',                 'Otros',         false, 200),
    ( 4, 'M', 'Mutua',                  'Mutua',         true,  70),
    ( 5, 'T', 'Talón',                  'Talón',         true,  80),
    ( 6, 'C', 'Tarjeta de crédito',     'Tarjeta',       true,  20),
    ( 7, 'F', 'Transferencia',          'Transferencia', true,  40),
    ( 8, 'N', 'Financiación',           'Financiación',  true,  60),
    ( 9, 'P', 'Efectivo pronto pago',   'Efectivo',      false, 110),
    (10, 'J', 'Tarjeta pronto pago',    'Tarjeta',       false, 120),
    (11, 'M', 'Mutua con tarjeta',      'Tarjeta',       false, 130),
    (12, 'M', 'Mutua con talón',        'Mutua',         false, 140),
    (13, NULL, 'Descuento en nómina',   'Otros',         false, 210),
    (14, NULL, 'Pago Eurodent',         'Eurodent',      false, 150),
    (15, NULL, 'Redondeo',              'Otros',         false, 220),
    (16, NULL, 'Bizum',                 'Bizum',         true,  30)
ON CONFLICT (id) DO NOTHING;

ALTER TABLE pagos ADD COLUMN IF NOT EXISTS forma_pago_id integer REFERENCES formas_pago(id);
CREATE INDEX IF NOT EXISTS ix_pagos_forma_pago_id ON pagos (forma_pago_id);

-- Relleno: texto de Gesden (TForPago.Descripcio) y variantes que ya hubiera escrito la app.
UPDATE pagos SET forma_pago_id = CASE forma_pago
        WHEN 'D Domiciliación'           THEN 1
        WHEN 'E En Efectivo'             THEN 2
        WHEN 'L Letras'                  THEN 3
        WHEN 'M Por Mutua'               THEN 4
        WHEN 'T Talón'                   THEN 5
        WHEN 'C Tarjeta de Crédito'      THEN 6
        WHEN 'F Transferencia Bancaria'  THEN 7
        WHEN 'N Financiación'            THEN 8
        WHEN 'P Efectivo pronto pago'    THEN 9
        WHEN 'J Tarjeta pronto pago'     THEN 10
        WHEN 'M Mutua Tarjeta'           THEN 11
        WHEN 'M Mutua Talón'             THEN 12
        WHEN 'Descuento Nómina'          THEN 13
        WHEN 'Pago Eurodent'             THEN 14
        WHEN 'Redondeo'                  THEN 15
        WHEN 'Efectivo'                  THEN 2
        WHEN 'En Efectivo'               THEN 2
        WHEN 'Tarjeta'                   THEN 6
        WHEN 'Tarjeta de Crédito'        THEN 6
        WHEN 'Transferencia'             THEN 7
        WHEN 'Transferencia Bancaria'    THEN 7
        WHEN 'Domiciliación'             THEN 1
        WHEN 'Financiación'              THEN 8
        WHEN 'Mutua'                     THEN 4
        WHEN 'Talón'                     THEN 5
        WHEN 'Bizum'                     THEN 16
    END
 WHERE forma_pago_id IS NULL AND forma_pago IS NOT NULL;

-- Si queda algún texto sin traducir, la migración se detiene (no se pierde ninguna forma en silencio).
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM pagos WHERE forma_pago IS NOT NULL AND forma_pago_id IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION '040: % pagos con forma de pago sin traducir a formas_pago', n;
    END IF;
END $$;

COMMIT;
