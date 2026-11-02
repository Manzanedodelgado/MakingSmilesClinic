-- Archivo de los ficheros de extracto bancario TAL CUAL se suben.
--
-- Hasta ahora el fichero (PDF/XLSX/CSV) se leía, se extraían los apuntes y se descartaba.
-- La asesoría necesita el ORIGINAL como soporte documental de los apuntes, así que se
-- guarda en /media/extractos (servido solo autenticado) y se registra aquí.

CREATE TABLE IF NOT EXISTS extractos_subidos (
  id                 SERIAL PRIMARY KEY,
  created_at         TIMESTAMP WITHOUT TIME ZONE,
  updated_at         TIMESTAMP WITHOUT TIME ZONE,
  centro_id          INTEGER NOT NULL REFERENCES centros(id),
  nombre_original    VARCHAR(255)  NOT NULL,
  archivo_url        VARCHAR(500)  NOT NULL,
  mime               VARCHAR(120),
  tamano_bytes       INTEGER       NOT NULL DEFAULT 0,
  hash_sha256        VARCHAR(64)   NOT NULL,
  subido_por         INTEGER REFERENCES usuarios(id),
  apuntes_importados INTEGER       NOT NULL DEFAULT 0,
  apuntes_omitidos   INTEGER       NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_extractos_centro ON extractos_subidos (centro_id);
CREATE INDEX IF NOT EXISTS ix_extractos_hash   ON extractos_subidos (hash_sha256);
CREATE INDEX IF NOT EXISTS ix_extractos_user   ON extractos_subidos (subido_por);
