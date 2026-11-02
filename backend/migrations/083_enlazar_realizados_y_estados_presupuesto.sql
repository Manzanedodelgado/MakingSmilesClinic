-- 083 · Enlazar actos de consulta con sus líneas y aplicar las reglas de estado (jmd, 18-oct-2026)
-- Un tratamiento se realiza (a) desde una línea de presupuesto o (b) creando el acto en SOAP. Se enlazan
-- los actos (b) con la línea que les corresponde: mismo paciente y mismo tratamiento (2.ª pasada: mismo
-- código), fecha del acto ≥ fecha de aceptación, por orden de fecha; mensualidad = tantos actos como
-- mensualidades. Pares calculados fuera: /tmp/083_pares.csv (acto, línea, presupuesto).
-- Reglas de estado (presupuestos aceptados 3/4/5/6):
--   todas las líneas realizadas → 5 Finalizado
--   > 6 meses desde la aceptación sin terminar → 7 Cancelado y sus líneas Previsto → 7 Cancelado
--   ≤ 6 meses con algo realizado → 4 En curso; sin nada → 3 Aceptado
-- Línea: 5 Realizado si tiene todos sus actos; si no, 3 Previsto.
BEGIN;
CREATE TEMP TABLE _p (rid int, lid int, pre int) ON COMMIT DROP;
\copy _p FROM '/tmp/083_pares.csv' WITH (FORMAT csv)
DO $$ DECLARE n int; BEGIN
    SELECT count(*) INTO n FROM _p p JOIN tratamientos_realizados tr ON tr.id = p.rid
     WHERE tr.presupuesto_linea_id IS NULL AND tr.estado_id = 5;
    IF n <> (SELECT count(*) FROM _p) THEN RAISE EXCEPTION '083: % de % actos ya no están libres', (SELECT count(*) FROM _p) - n, (SELECT count(*) FROM _p); END IF;
END $$;
UPDATE tratamientos_realizados tr SET presupuesto_linea_id = p.lid, updated_at = now() FROM _p p WHERE tr.id = p.rid;

CREATE TEMP TABLE _lin ON COMMIT DROP AS
SELECT l.id, l.presupuesto_id,
       CASE WHEN t.es_mensualidad THEN greatest(coalesce(l.cantidad,1),1) ELSE 1 END AS need,
       (SELECT count(*) FROM tratamientos_realizados tr WHERE tr.presupuesto_linea_id = l.id AND tr.estado_id = 5) AS hechos
  FROM presupuesto_lineas l JOIN tratamientos t ON t.id = l.tratamiento_id
  JOIN presupuestos p ON p.id = l.presupuesto_id
 WHERE l.estado IN (3, 5) AND p.estado_id IN (3, 4, 5, 6);

CREATE TEMP TABLE _pre ON COMMIT DROP AS
SELECT p.id, CASE WHEN count(*) FILTER (WHERE x.hechos < x.need) = 0 THEN 5
                  WHEN coalesce(p.fecha_aceptacion, p.fecha) < current_date - interval '6 months' THEN 7
                  WHEN count(*) FILTER (WHERE x.hechos > 0) > 0 THEN 4 ELSE 3 END AS nuevo
  FROM presupuestos p JOIN _lin x ON x.presupuesto_id = p.id GROUP BY p.id;

UPDATE presupuesto_lineas l SET estado = CASE
         WHEN x.hechos >= x.need THEN 5
         WHEN pr.nuevo = 7 THEN 7
         ELSE 3 END, updated_at = now()
  FROM _lin x JOIN _pre pr ON pr.id = x.presupuesto_id
 WHERE l.id = x.id;
UPDATE presupuestos p SET estado_id = pr.nuevo, updated_at = now() FROM _pre pr WHERE p.id = pr.id AND p.estado_id <> pr.nuevo;
COMMIT;
