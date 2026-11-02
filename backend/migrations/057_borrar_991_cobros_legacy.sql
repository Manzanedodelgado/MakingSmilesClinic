-- 057 · Borrar de MakingSmiles los 991 cobros negativos de la aplicación anterior (jmd, 17-oct-2026)
-- En GELITE son líneas de TtosMed con StaTto=5 e importe negativo (929 "Cobro", 54 "DESCUENTO",
-- 5 "DEVOLUCIÓN", 1 "TRASPASO DE SALDO", 1 "COLOCACIÓN ORTODONCIA AUTOLIGABLE", 1 "TRATAMIENTO"),
-- 2001-2019, −239.095,85 €, con su cargo negativo en DeudaCli. No están en PagoCli.
-- En la app estaban DUPLICADOS: negativos en tratamientos_realizados (migración 051) y positivos
-- en pagos como Eurodent con num_transaccion 'TR<id>' (migraciones 042/043).
-- Orden del usuario: borrarlos todos de la BD. Nada depende de ellos (comprobado: 0 fases,
-- 0 líneas de presupuesto, 0 deudas, 0 deuda_pago, 0 movimientos bancarios).
BEGIN;

DELETE FROM tratamientos_realizados WHERE importe < 0;
DELETE FROM pagos WHERE num_transaccion LIKE 'TR%';

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM tratamientos_realizados WHERE importe < 0;
    IF n > 0 THEN RAISE EXCEPTION '057: quedan % negativos en realizados', n; END IF;
    SELECT count(*) INTO n FROM pagos WHERE num_transaccion LIKE 'TR%';
    IF n > 0 THEN RAISE EXCEPTION '057: quedan % pagos TR', n; END IF;
END $$;

COMMIT;
