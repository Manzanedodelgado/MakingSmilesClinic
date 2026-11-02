-- 088 · id_cita único (jmd, 18-oct-2026)
-- Orden del usuario: IdCita es único; su fila va actualizando su estado y se registra la modificación.
-- En Gesden un IdCita se reutiliza (cita movida: la vieja Anulada + la nueva con el mismo número).
-- Por cada id_cita repetido queda la versión VIGENTE (no anulada/cancelada; después la de alta más
-- reciente) y las demás se guardan en auditoria como 'agenda.cita.version_anterior' (detalle = la fila
-- completa, fecha = la de su último estado) y se quitan de citas. Después: índice único y contador.
BEGIN;
CREATE TEMP TABLE _orden ON COMMIT DROP AS
SELECT id, id_cita,
       row_number() OVER (PARTITION BY id_cita
                          ORDER BY (estado_id IN (1, 8)), fecha_alta DESC NULLS LAST, fecha DESC, hora DESC, id DESC) AS n
  FROM citas WHERE id_cita IS NOT NULL;
CREATE TEMP TABLE _vig ON COMMIT DROP AS SELECT id_cita, id FROM _orden WHERE n = 1;

INSERT INTO auditoria (created_at, updated_at, centro_id, accion, recurso, detalle, exito)
SELECT coalesce(c.fecha_hora_estado, c.fecha_alta, now()), now(), c.centro_id, 'agenda.cita.version_anterior',
       'cita:' || v.id,
       json_build_object('origen', 'Gesden (IdCita reutilizado)', 'id_cita', c.id_cita, 'version',
                         to_jsonb(c) - 'created_at' - 'updated_at'), true
  FROM citas c JOIN _orden o ON o.id = c.id AND o.n > 1 JOIN _vig v ON v.id_cita = c.id_cita;

DELETE FROM citas c USING _orden o WHERE o.id = c.id AND o.n > 1;

CREATE UNIQUE INDEX ux_citas_id_cita ON citas (id_cita) WHERE id_cita IS NOT NULL;
SELECT setval('citas_id_cita_seq', (SELECT max(id_cita) FROM citas));
COMMIT;
