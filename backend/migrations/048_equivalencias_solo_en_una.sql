-- 048 · Completa gelite_equivalencias con los catálogos que existen solo en una de las dos bases
-- (jmd, 17-oct-2026). Gabinetes, especialidades, razones sociales y tipos de antecedente.
BEGIN;
\copy gelite_equivalencias (entidad,id_gelite,nombre_gelite,id_app,nombre_app,estado,filas_usando,nota) FROM '/tmp/equiv2.tsv' WITH (FORMAT text, NULL '\N')

-- Entidades completas que existen en una base y no en la otra, o cuya contraparte no se ha localizado.
INSERT INTO gelite_equivalencias (entidad, id_gelite, nombre_gelite, id_app, nombre_app, estado, filas_usando, nota) VALUES
 ('agendas', NULL,'(no localizada en GELITE)', 4,'Agenda 1','FALTA EN GELITE', 49430,
  'La app tiene una sola agenda, la 4. No se ha encontrado su tabla en GELITE: AgdNotas, AgdAccesos, TAgdOpc no son el catálogo. PENDIENTE de localizar.'),
 ('paciente_seguros', NULL,'(no localizada en GELITE)', NULL,'paciente_seguros (0 filas)','FALTA EN GELITE', 0,
  'Tabla de seguros del paciente vacía en la app y sin contraparte encontrada en GELITE.'),
 ('talonarios', NULL,'TalonReceta / RegTalones', NULL,'talonarios (0 filas)','FALTA EN LA APP', 0,
  'GELITE tiene TalonReceta y RegTalones; en la app talonarios y talonario_recetas están vacías.'),
 ('estados_presupuesto', 0,'Presu.Estado=0 (250 filas)', NULL,'repartido entre 0,1 y 2','DISTINTO', 250,
  'GELITE: 250 en estado 0 y 2.089 en el 1. La app los reparte entre 0 (3), 1 (34) y 2/Anulado (2.302). Suma igual (2.339) pero reclasificados. PENDIENTE confirmar si es deliberado.'),
 ('centros', 1,'(verificar)', 1,'RUBIO GARCIA DENTAL','DISTINTO', NULL,
  'GELITE tiene además el centro 2, con el MISMO nombre RUBIO GARCIA DENTAL, y el -1 (Center by default). Hay que ver si el 1 y el 2 son el mismo centro duplicado.');
COMMIT;
