-- 053 · Los actos del IdCol 6 de GELITE pasan a Lucía Guillén (jmd, 17-oct-2026)
-- En GELITE el IdCol 6 se llama literalmente "." — un registro basura del catálogo, sin nombre.
-- Tiene 71 actos clínicos reales (curetajes, obturaciones, reconstrucciones, coronas) del
-- 18-06-2013 al 01-08-2015, por 3.721,00 €, que quedaban sin doctor en la app.
-- Decisión del usuario (17-oct-2026): son de Lucía Guillén Abasolo = IdCol 2 en GELITE,
-- colaborador 1 en MakingSmiles.
--
-- Esto hace que la producción de la app ya NO sea idéntica a la de GELITE por doctor:
-- Lucía suma 3.721,00 € que en GELITE figuran bajo el 6. Queda declarado en
-- gelite_equivalencias para que cuadra.py no lo tome por un error.
BEGIN;

CREATE TABLE IF NOT EXISTS tratamientos_realizados_colab_bk_053 AS
    SELECT id, colaborador_id FROM tratamientos_realizados
     WHERE origen_id_gelite IS NOT NULL AND colaborador_id IS NULL;

UPDATE tratamientos_realizados r
   SET colaborador_id = (SELECT id FROM colaboradores WHERE id_gelite = 2),
       updated_at = now()
 WHERE r.id IN (SELECT id FROM tratamientos_realizados_colab_bk_053);

INSERT INTO gelite_equivalencias
    (entidad, id_gelite, nombre_gelite, id_app, nombre_app, estado, filas_usando, revisado, nota)
VALUES ('colaboradores', 6, '. (etiqueta sin nombre)',
        (SELECT id FROM colaboradores WHERE id_gelite = 2), 'LUCIA GUILLEN ABASOLO',
        'DISTINTO', 71, true,
        'Decisión del usuario 17-oct-2026: los 71 actos del IdCol 6 (2013-2015, 3.721,00 €) son '
        'de Lucía Guillén. La producción por doctor de la app ya NO coincide con GELITE en el 2 '
        'ni en el 6: es intencionado.');

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM tratamientos_realizados
     WHERE origen = 'GELITE:TtosMed' AND colaborador_id IS NULL;
    IF n > 0 THEN RAISE EXCEPTION '053: quedan % actos sin doctor', n; END IF;
END $$;

COMMIT;
