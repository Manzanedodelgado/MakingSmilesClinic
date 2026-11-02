-- 087 · Equivalencias de COLUMNAS de pacientes Gesden ↔ app en gelite_equivalencias (jmd, 18-oct-2026)
-- Pacientes.IdPac  (interno, no público) → pacientes.id
-- Pacientes.NumPac (público)             → pacientes.num_historia
BEGIN;
DELETE FROM gelite_equivalencias WHERE entidad = 'pacientes' AND id <> 83;
INSERT INTO gelite_equivalencias (id, entidad, id_gelite, nombre_gelite, id_app, nombre_app, estado, filas_usando, revisado, nota)
VALUES (83, 'pacientes', NULL, 'Pacientes.IdPac', NULL, 'pacientes.id', 'COINCIDE', 6250, false,
        '6.250 filas, mismo id, mismo mínimo (18) y máximo (7014)')
ON CONFLICT (id) DO UPDATE SET entidad = EXCLUDED.entidad, id_gelite = EXCLUDED.id_gelite, nombre_gelite = EXCLUDED.nombre_gelite,
    id_app = EXCLUDED.id_app, nombre_app = EXCLUDED.nombre_app, estado = EXCLUDED.estado, filas_usando = EXCLUDED.filas_usando,
    revisado = EXCLUDED.revisado, nota = EXCLUDED.nota;
INSERT INTO gelite_equivalencias (entidad, id_gelite, nombre_gelite, id_app, nombre_app, estado, filas_usando, revisado, nota)
VALUES ('pacientes', NULL, 'Pacientes.NumPac', NULL, 'pacientes.num_historia', 'COINCIDE', 6250, false,
        'NUMPAC = número público del paciente; IdPac es interno. 6.250 de 6.250 coinciden');
COMMIT;
