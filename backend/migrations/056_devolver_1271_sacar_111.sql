-- 056 · Deshacer la 055: vuelven las notas MENOS las 111 que hablan de dinero (jmd, 17-oct-2026)
-- La 055 sacó las 1.382 cuando lo señalado eran solo las 111 que mencionan pagos y no
-- coincidían con un cobro del mismo día. Vuelven 1.271 con su id original; las 111 se quedan
-- fuera, en notas_gelite_sin_tratamiento.
BEGIN;

INSERT INTO tratamientos_realizados
    (created_at, updated_at, id, centro_id, paciente_id, cliente_id, num_tto, tratamiento_id,
     presupuesto_linea_id, colaborador_id, colaborador_aux_id, piezas, zona_boca,
     fecha_inicio, fecha_fin, actos, tiempo_min, importe, descuento, importe_descuento,
     importe_privado, importe_mutua, pendiente, num_factura_e, num_transaccion, notas,
     campo_libre_1, tarifa_precio_id, estado_id, descuento_aplica_doctor, coste_laboratorio,
     caras, origen, origen_id_gelite, origen_fecha)
SELECT created_at, updated_at, id, centro_id, paciente_id, cliente_id, num_tto, tratamiento_id,
       presupuesto_linea_id, colaborador_id, colaborador_aux_id, piezas, zona_boca,
       fecha_inicio, fecha_fin, actos, tiempo_min, importe, descuento, importe_descuento,
       importe_privado, importe_mutua, pendiente, num_factura_e, num_transaccion, notas,
       campo_libre_1, tarifa_precio_id, estado_id, descuento_aplica_doctor, coste_laboratorio,
       caras, origen, origen_id_gelite, origen_fecha
  FROM notas_gelite_sin_tratamiento
 WHERE NOT (NOT revisar AND notas ~* 'paga|abona|cobr|pago|mensual|euros|abono|saldo');

DELETE FROM notas_gelite_sin_tratamiento
 WHERE NOT (NOT revisar AND notas ~* 'paga|abona|cobr|pago|mensual|euros|abono|saldo');

SELECT setval(pg_get_serial_sequence('tratamientos_realizados','id'),
              (SELECT max(id) FROM tratamientos_realizados));

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM tratamientos_realizados;
    IF n <> 40758 THEN RAISE EXCEPTION '056: hay % filas, se esperaban 40.758', n; END IF;
    SELECT count(*) INTO n FROM notas_gelite_sin_tratamiento;
    IF n <> 111 THEN RAISE EXCEPTION '056: quedan % notas fuera, se esperaban 111', n; END IF;
END $$;

COMMIT;
