-- 047 · Tabla de equivalencias de identificadores GELITE <-> MakingSmiles (jmd, 17-oct-2026)
-- Catálogo por catálogo y fila por fila: qué número tiene cada cosa en GELITE, qué número tiene
-- en la app, y si coinciden, difieren o faltan en una de las dos. Nace de la auditoría del
-- 17-oct-2026, que encontró que los doctores y los tipos de cita se migraron con el número de
-- GELITE sin traducir, atribuyendo la producción y el tipo de visita a quien no era.
BEGIN;

DROP TABLE IF EXISTS gelite_equivalencias;
CREATE TABLE gelite_equivalencias (
    id            serial PRIMARY KEY,
    entidad       text    NOT NULL,   -- catálogo (colaboradores, tipos_cita, ...)
    id_gelite     integer,            -- su id en GELITE; NULL = no existe allí
    nombre_gelite text,
    id_app        integer,            -- su id en MakingSmiles; NULL = no existe aquí
    nombre_app    text,
    estado        text    NOT NULL,   -- COINCIDE | DISTINTO | FALTA EN LA APP | FALTA EN GELITE
    filas_usando  integer,            -- cuántas filas de la app usan hoy ese id
    revisado      boolean NOT NULL DEFAULT false,
    nota          text
);
COMMENT ON TABLE gelite_equivalencias IS
 'Equivalencia de ids entre GELITE y MakingSmiles. Fuente de verdad al migrar: antes de volcar '
 'una tabla hay que traducir sus ids con esta equivalencia, nunca copiarlos en bruto.';

\copy gelite_equivalencias (entidad,id_gelite,nombre_gelite,id_app,nombre_app,estado,filas_usando) FROM '/tmp/equivalencias.tsv' WITH (FORMAT text, NULL '\N')

CREATE INDEX gelite_equivalencias_entidad_idx ON gelite_equivalencias (entidad, estado);

-- Los catálogos cuyos ids SÍ coinciden uno a uno, comprobados en la auditoría.
INSERT INTO gelite_equivalencias (entidad, id_gelite, nombre_gelite, id_app, nombre_app, estado, filas_usando, nota) VALUES
 ('pacientes',   NULL,'Pacientes.IdPac',  NULL,'pacientes.id',   'COINCIDE', 6250,'6.250 filas, mismo id, mismo mínimo (18) y máximo (7014)'),
 ('clientes',    NULL,'Clientes.IdCli',   NULL,'clientes.id',    'COINCIDE', 6290,'6.290 filas, mismo id'),
 ('tratamientos',NULL,'Tratamientos.IdTratamiento', NULL,'tratamientos.id','COINCIDE', 606,'mismo id y mismo código'),
 ('estados_tratamiento', 5,'StaTto=5 (Realizado)', 5,'Realizado','COINCIDE', 39878,'los estados de TtosMed se conservan');

COMMIT;
