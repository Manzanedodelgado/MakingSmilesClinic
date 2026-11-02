-- 049 · Rehacer las filas de colaboradores en gelite_equivalencias (jmd, 17-oct-2026)
-- La comparación anterior era POSICIONAL (el id 23 de GELITE contra el id 23 de la app) y daba
-- falsos ausentes: Lydia Ábalos es la 23 en GELITE y existe en la app como la 20, con su
-- id_gelite ya puesto. Lo correcto es comparar por la equivalencia real (colaboradores.id_gelite).
BEGIN;

DELETE FROM gelite_equivalencias WHERE entidad = 'colaboradores';

INSERT INTO gelite_equivalencias (entidad, id_gelite, nombre_gelite, id_app, nombre_app, estado, filas_usando, revisado, nota)
SELECT 'colaboradores', c.id_gelite, u.nombre||' '||coalesce(u.apellidos,''), c.id,
       u.nombre||' '||coalesce(u.apellidos,''),
       'DISTINTO', (SELECT count(*) FROM tratamientos_realizados r WHERE r.colaborador_id = c.id),
       true, 'Enlazado por colaboradores.id_gelite. El número cambia entre las dos bases.'
  FROM colaboradores c JOIN usuarios u ON u.id = c.id
 WHERE c.id_gelite IS NOT NULL AND c.id_gelite <> c.id;

INSERT INTO gelite_equivalencias (entidad, id_gelite, nombre_gelite, id_app, nombre_app, estado, filas_usando, revisado, nota)
SELECT 'colaboradores', c.id_gelite, u.nombre||' '||coalesce(u.apellidos,''), c.id,
       u.nombre||' '||coalesce(u.apellidos,''), 'COINCIDE',
       (SELECT count(*) FROM tratamientos_realizados r WHERE r.colaborador_id = c.id), true,
       'Mismo número en las dos bases.'
  FROM colaboradores c JOIN usuarios u ON u.id = c.id
 WHERE c.id_gelite = c.id;

INSERT INTO gelite_equivalencias (entidad, id_gelite, nombre_gelite, id_app, nombre_app, estado, filas_usando, nota)
SELECT 'colaboradores', NULL, NULL, c.id, coalesce(u.nombre||' '||coalesce(u.apellidos,''),'(sin usuario)'),
       'FALTA EN GELITE', (SELECT count(*) FROM tratamientos_realizados r WHERE r.colaborador_id = c.id),
       'No viene de GELITE: creado en la app.'
  FROM colaboradores c LEFT JOIN usuarios u ON u.id = c.id
 WHERE c.id_gelite IS NULL;

COMMIT;
