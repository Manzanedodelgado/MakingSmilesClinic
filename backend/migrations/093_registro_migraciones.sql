-- 093: registro de migraciones aplicadas.
--
-- Por qué existe: el 18-oct-2026 el backend se desplegó usando cuatro columnas
-- (tratamientos_realizados.factura_documento_id, documentos_paciente.factura_origen_id y
-- .motivo_rectificacion, pagos.motivo) cuyas migraciones (091, 092) nunca se habían
-- aplicado. Resultado: 16 errores UndefinedColumn en producción y leer un tratamiento
-- rompía. Nadie se enteró porque NO HABÍA FORMA DE SABER qué estaba aplicado y qué no:
-- el único indicio era ir columna por columna preguntándole al information_schema.
--
-- Esta tabla es ese indicio que faltaba. No aplica nada ni valida nada por sí sola: es el
-- cuaderno donde migra.sh anota lo que ejecuta, para que la pregunta "¿va la BD por detrás
-- del código?" tenga respuesta en una consulta en vez de en una investigación.
--
-- `nombre` es el fichero tal cual (no un número): en backend/migrations hay números
-- repetidos (003, 004, 007, 008 y 091 están duplicados), así que el número NO identifica
-- una migración y usarlo como clave perdería una de cada pareja.
CREATE TABLE IF NOT EXISTS migraciones_aplicadas (
    nombre      varchar(200) PRIMARY KEY,          -- p. ej. '091_rectificativas_pacientes.sql'
    aplicada_en timestamp NOT NULL DEFAULT NOW(),
    -- Cómo se supo. 'migra.sh' = anotada al ejecutarse. 'retroactiva' = el esquema ya tenía
    -- lo que la migración crea, comprobado contra information_schema, pero NO se sabe
    -- cuándo ni quién la aplicó: la fecha es la del sembrado, no la de la migración.
    origen      varchar(30) NOT NULL DEFAULT 'migra.sh',
    nota        varchar(500)
);

COMMENT ON TABLE migraciones_aplicadas IS
    'Qué migraciones de backend/migrations se han aplicado a esta BD. La escribe scripts/migra.sh.';
COMMENT ON COLUMN migraciones_aplicadas.origen IS
    'migra.sh = anotada al ejecutar. retroactiva = deducida del esquema al crear el registro (fecha no fiable).';
