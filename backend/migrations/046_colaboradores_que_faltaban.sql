-- 046 · Alta de los doctores de GELITE que no tenían ficha de colaborador (jmd, 17-oct-2026)
-- Existían en `usuarios` pero sin fila en `colaboradores`, que es la tabla que da nombre al
-- doctor de un tratamiento y la que usa la liquidación. Por eso su producción salía sin nombre.
-- Se crean inactivos (ya no trabajan en la clínica) y con su id_gelite puesto.
-- PRIMERAS VISITAS (IdCol 7 de GELITE) no es una persona sino una etiqueta de agenda, pero
-- tiene 149.437,96 € de producción registrada, así que se crea igual para no perder el dato.
BEGIN;

INSERT INTO usuarios (created_at, updated_at, id, nombre, apellidos)
VALUES (now(), now(), 26, 'PRIMERAS VISITAS', '(etiqueta Gesden)')
ON CONFLICT (id) DO NOTHING;
SELECT setval('usuarios_id_seq', GREATEST((SELECT max(id) FROM usuarios WHERE id < 9000), 26));

INSERT INTO colaboradores (created_at, updated_at, id, activo, aplica_laboratorio, aplica_irpf,
                           factura_produccion, id_gelite, id_col)
VALUES (now(), now(),  1, false, false, false, false,  2,  1),   -- Lucía Guillén Abasolo
       (now(), now(),  5, false, false, false, false,  9,  5),   -- Marta Pérez del Real
       (now(), now(),  6, false, false, false, false, 10,  6),   -- Yolanda Ballesteros
       (now(), now(),  7, false, false, false, false, 11,  7),   -- Águeda Díaz Blas
       (now(), now(), 13, false, false, false, false, 17, 13),   -- José Manuel Rizo Fernández
       (now(), now(), 22, false, false, false, false, 25, 22),   -- Ignacio Ferrero García
       (now(), now(), 26, false, false, false, false,  7, 26)    -- PRIMERAS VISITAS (etiqueta)
ON CONFLICT (id) DO NOTHING;

SELECT setval('colaboradores_id_seq', (SELECT max(id) FROM colaboradores));

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM colaboradores WHERE id_gelite IS NULL;
    IF n > 1 THEN RAISE EXCEPTION '046: quedan % colaboradores sin id_gelite (se espera solo ALICIA)', n; END IF;
END $$;

COMMIT;
