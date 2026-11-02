-- 085 · Presupuestos con implantes: 9 meses de validez en vez de 6 (jmd, 18-oct-2026)
-- Implantes = presupuesto con alguna línea de COLOCACIÓN de implante (tratamientos 127, 187, 293, 295,
-- 321, 525, 613, 614). No cuentan solas coronas sobre implante, estudio, revisiones ni limpiezas.
-- Si además es de ortodoncia (084) conserva los 24 meses. Misma regla de 083 con 9 meses.
BEGIN;
CREATE TEMP TABLE _orto ON COMMIT DROP AS
SELECT DISTINCT l.presupuesto_id AS id FROM presupuesto_lineas l JOIN tratamientos t ON t.id = l.tratamiento_id
 WHERE t.nombre ~* 'mensualidad' OR (l.estado = 5 AND t.nombre ~* '^(estudio ortodoncia|colocaci.n ortodoncia)');
CREATE TEMP TABLE _impl ON COMMIT DROP AS
SELECT DISTINCT l.presupuesto_id AS id FROM presupuesto_lineas l
 WHERE l.tratamiento_id IN (127, 187, 293, 295, 321, 525, 613, 614)
   AND l.presupuesto_id NOT IN (SELECT id FROM _orto);

CREATE TEMP TABLE _lin ON COMMIT DROP AS
SELECT l.id, l.presupuesto_id,
       CASE WHEN t.es_mensualidad THEN greatest(coalesce(l.cantidad,1),1) ELSE 1 END AS need,
       (SELECT count(*) FROM tratamientos_realizados tr WHERE tr.presupuesto_linea_id = l.id AND tr.estado_id = 5) AS hechos
  FROM presupuesto_lineas l JOIN tratamientos t ON t.id = l.tratamiento_id
  JOIN presupuestos p ON p.id = l.presupuesto_id
 WHERE l.presupuesto_id IN (SELECT id FROM _impl) AND l.estado IN (3, 5, 7) AND p.estado_id IN (3, 4, 5, 6, 7);

CREATE TEMP TABLE _pre ON COMMIT DROP AS
SELECT p.id, CASE WHEN count(*) FILTER (WHERE x.hechos < x.need) = 0 THEN 5
                  WHEN coalesce(p.fecha_aceptacion, p.fecha) < current_date - interval '9 months' THEN 7
                  WHEN count(*) FILTER (WHERE x.hechos > 0) > 0 THEN 4 ELSE 3 END AS nuevo
  FROM presupuestos p JOIN _lin x ON x.presupuesto_id = p.id GROUP BY p.id;

UPDATE presupuesto_lineas l SET estado = CASE WHEN x.hechos >= x.need THEN 5 WHEN pr.nuevo = 7 THEN 7 ELSE 3 END,
       updated_at = now()
  FROM _lin x JOIN _pre pr ON pr.id = x.presupuesto_id
 WHERE l.id = x.id AND l.estado <> CASE WHEN x.hechos >= x.need THEN 5 WHEN pr.nuevo = 7 THEN 7 ELSE 3 END;
UPDATE presupuestos p SET estado_id = pr.nuevo, updated_at = now() FROM _pre pr WHERE p.id = pr.id AND p.estado_id <> pr.nuevo;
COMMIT;
