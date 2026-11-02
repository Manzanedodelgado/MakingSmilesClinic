-- Vinculación exacta de actos facturados y archivo de rectificativas desde Pacientes.
--
-- Había un segundo fichero con este MISMO número, 091_rectificativas_documentos_paciente.sql,
-- con dos de estas cinco sentencias. Se borró el 19-oct-2026 por ser redundante: el número
-- repetido hacía imposible saber cuál se había aplicado, y de hecho esta se aplicó a medias
-- (las columnas sí, el UPDATE de abajo no). Un número = una migración.
BEGIN;
ALTER TABLE tratamientos_realizados
    ADD COLUMN IF NOT EXISTS factura_documento_id integer REFERENCES documentos_admin(id);
CREATE INDEX IF NOT EXISTS ix_tratamientos_realizados_factura_documento_id
    ON tratamientos_realizados (factura_documento_id);
ALTER TABLE documentos_paciente
    ADD COLUMN IF NOT EXISTS factura_origen_id integer REFERENCES documentos_admin(id),
    ADD COLUMN IF NOT EXISTS motivo_rectificacion varchar(500);
CREATE INDEX IF NOT EXISTS ix_documentos_paciente_factura_origen_id
    ON documentos_paciente (factura_origen_id);
WITH candidatos AS (
    SELECT tr.id AS acto_id, min(da.id) AS factura_id, count(da.id) AS n
      FROM tratamientos_realizados tr
      JOIN documentos_admin da ON da.centro_id = tr.centro_id
       AND concat(coalesce(da.serie, ''), da.num_doc::text) = trim(tr.num_factura_e)
     WHERE tr.num_factura_e IS NOT NULL AND trim(tr.num_factura_e) <> ''
       AND da.num_doc IS NOT NULL
     GROUP BY tr.id
)
UPDATE tratamientos_realizados tr SET factura_documento_id = c.factura_id
  FROM candidatos c WHERE c.acto_id = tr.id AND c.n = 1;
COMMIT;
