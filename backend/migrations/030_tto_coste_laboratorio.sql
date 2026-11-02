-- 030 · Coste de laboratorio del acto realizado (Gestoría → Producción → Tratamientos).
--
-- El coste de laboratorio de un tratamiento no estaba en ninguna parte utilizable: la
-- liquidación del doctor lo leía de `tarifa_precios.coste_laboratorio`, que está a 0 en las
-- 595 filas del catálogo, y además el 99,8 % de los actos tiene `tarifa_precio_id` a NULL,
-- así que nunca llegaba a leerse nada. La .37 lo guardaba por colaborador×tratamiento
-- (tabla `colab_tratamientos`), detalle que se perdió en la migración.
--
-- Aquí se guarda POR ACTO, que es donde el coste es un hecho (esta corona, este laboratorio,
-- este importe) y no una media del catálogo. NULL = sin informar (distinto de 0 € informado).
ALTER TABLE tratamientos_realizados
    ADD COLUMN IF NOT EXISTS coste_laboratorio NUMERIC(10, 2);
