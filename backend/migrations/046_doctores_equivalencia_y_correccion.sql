-- 046 · Alta de los doctores que faltaban y CORRECCIÓN del doctor de cada acto (jmd, 17-oct-2026)
--
-- PROBLEMA: la migración guardó en tratamientos_realizados.colaborador_id el IdCol de GELITE
-- SIN traducirlo. En la app esos números pertenecen a OTRAS personas, así que toda la
-- producción estaba mal atribuida: los 1.415.985,81 € de Mario Rubio (IdCol 4 en GELITE)
-- figuraban a nombre de Irene García (id 4 en la app), y así con todos.
--
-- Además seis doctores de GELITE existían en `usuarios` pero sin fila en `colaboradores`,
-- que es la tabla que da nombre al doctor y la que usa la liquidación: Lucía Guillén,
-- Marta Pérez del Real, Yolanda Ballesteros, Águeda Díaz Blas, José Manuel Rizo e Ignacio
-- Ferrero. Se crean inactivos. PRIMERAS VISITAS (IdCol 7) no es persona sino etiqueta de
-- agenda, pero tiene 149.437,96 € registrados, así que se crea también.
--
-- El doctor correcto se vuelve a leer de GELITE (TtosMed.IdCol) por (IdPac, NumTto).
BEGIN;

-- 1 · altas que faltaban
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

-- ALICIA: en GELITE es la IdCol 13 ("ALICIA"), en la app el colaborador 9 ("ALICIA ALICIA").
UPDATE colaboradores SET id_gelite = 13 WHERE id = 9 AND id_gelite IS NULL;
-- El 31 es el cajón que la migración creó para las etiquetas sin nombre de GELITE (5 y 6).
UPDATE colaboradores SET id_gelite = 5 WHERE id = 31 AND id_gelite IS NULL;

-- 2 · copia de seguridad del doctor actual, para poder deshacer
CREATE TABLE IF NOT EXISTS tratamientos_realizados_colab_bk_046 AS
    SELECT id, colaborador_id FROM tratamientos_realizados;

-- 3 · el doctor correcto, leído de GELITE
CREATE TEMP TABLE _gel_col (id_pac int, num_tto int, id_col_gelite int) ON COMMIT DROP;
\copy _gel_col FROM '/tmp/col_map_rows.tsv' WITH (FORMAT text, NULL '\N')

UPDATE tratamientos_realizados r
   SET colaborador_id = c.id, updated_at = now()
  FROM _gel_col g
  JOIN colaboradores c ON c.id_gelite = g.id_col_gelite
 WHERE r.paciente_id = g.id_pac AND r.num_tto = g.num_tto
   AND r.colaborador_id IS DISTINCT FROM c.id;

-- El IdCol 6 de GELITE ("." sin nombre) va al mismo cajón que el 5.
UPDATE tratamientos_realizados r SET colaborador_id = 31, updated_at = now()
  FROM _gel_col g
 WHERE r.paciente_id = g.id_pac AND r.num_tto = g.num_tto
   AND g.id_col_gelite = 6 AND r.colaborador_id IS DISTINCT FROM 31;

-- 4 · ningún acto puede apuntar a un colaborador inexistente
DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM tratamientos_realizados r
     WHERE r.colaborador_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM colaboradores c WHERE c.id = r.colaborador_id);
    IF n > 0 THEN RAISE EXCEPTION '046: % actos apuntan a un colaborador que no existe', n; END IF;
END $$;

COMMIT;
