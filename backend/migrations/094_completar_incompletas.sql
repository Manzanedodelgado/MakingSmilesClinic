-- 094: completa lo que el registro de migraciones (093) descubrió a medio aplicar.
--
-- Al sembrar migraciones_aplicadas aparecieron 11 migraciones con objetos ausentes. Revisadas
-- una a una, solo estas son trabajo real pendiente; el resto quedaron DESCARTADAS y por qué
-- está escrito en la nota de cada una dentro del registro:
--   · 014 y 081 → obsoletas: migraciones posteriores (026, 082) retiraron a propósito lo que
--     ellas creaban. Aplicarlas ahora resucitaría algo ya decidido en contra.
--   · platform_001 → sí está aplicada, pero en makingsmiles_platform (su cabecera lo dice).
--   · uq_gasto_incid_msg (008) → NO se puede: gasto_incidencias tiene 2.009 filas para 1.642
--     correos (157 repetidos, alguno 6 veces). El índice es único; hay que decidir primero qué
--     se hace con esos duplicados, y eso no es una migración, es una limpieza de datos.
--
-- Todo lo de aquí son índices (y una columna que el modelo ya declara): ninguno cambia datos.
BEGIN;

-- 024 · orden de dispensación de las líneas de receta (las columnas ya estaban)
CREATE INDEX IF NOT EXISTS ix_receta_lineas_orden
    ON public.receta_lineas (receta_id, orden_dispensacion);

-- 030 · consulta viva: las tres búsquedas de recomendaciones_paciente
CREATE INDEX IF NOT EXISTS idx_recomendaciones_paciente_centro_id
    ON recomendaciones_paciente (centro_id);
CREATE INDEX IF NOT EXISTS idx_recomendaciones_paciente_paciente_id
    ON recomendaciones_paciente (paciente_id);
CREATE INDEX IF NOT EXISTS idx_recomendaciones_paciente_cita_id
    ON recomendaciones_paciente (cita_id);

-- 032 · tipo de consentimiento del tratamiento (la columna ya estaba)
CREATE INDEX IF NOT EXISTS ix_tratamientos_consentimiento_tipo
    ON public.tratamientos (consentimiento_tipo);

-- 038 · catálogo geográfico oficial: sin duplicados comprobados, los UNIQUE entran
CREATE UNIQUE INDEX IF NOT EXISTS uq_provincias_pais_ine ON provincias (pais_id, ine_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_municipios_provincia_ine ON municipios (provincia_id, ine_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_cpgeo_cp_municipio ON codigos_postales_geo (cp, municipio_id);

-- 089 · financieras por centro
CREATE INDEX IF NOT EXISTS ix_financieras_centro ON financieras (centro_id);

-- 090 · saldo por paciente: la tabla y los triggers sí se aplicaron, los índices no
CREATE INDEX IF NOT EXISTS ix_saldo_paciente_centro ON saldo_paciente (centro_id);
CREATE INDEX IF NOT EXISTS ix_saldo_paciente_saldo ON saldo_paciente (saldo) WHERE saldo <> 0;

-- 073 · paso 1 de 2 que se quedó a medias: la tabla laboratorio_trabajos existe y la 074 (que
-- quitaba las columnas viejas) ya corrió, pero esta columna nunca se añadió. domain/models la
-- declara, así que la BD iba por detrás del modelo igual que con la 091.
ALTER TABLE tarifa_precios
    ADD COLUMN IF NOT EXISTS laboratorio_trabajo_id integer REFERENCES laboratorio_trabajos(id);
CREATE INDEX IF NOT EXISTS ix_tarifa_precios_laboratorio_trabajo_id
    ON tarifa_precios (laboratorio_trabajo_id);

COMMIT;
