-- 097: permisos por PESTAÑA dentro de cada área (Pacientes, Gestoría, Configuración).
-- Una pestaña solo cuenta si la persona tiene también el permiso del área (<area>.ver).
-- SIN CAMBIO DE ACCESO HOY: quien ya tenía el área (por rol o por permiso directo) recibe todas
-- sus pestañas; a quien el rol se las daría pero no tenía el área se le deniegan, como en 096.
BEGIN;

CREATE TEMP TABLE _tabs (codigo text, descripcion text, area text) ON COMMIT DROP;
INSERT INTO _tabs VALUES
 ('pacientes.tab.ficha','Pacientes · pestaña Ficha','pacientes.ver'),
 ('pacientes.tab.filiacion','Pacientes · pestaña Filiación','pacientes.ver'),
 ('pacientes.tab.presupuestos','Pacientes · pestaña Presupuestos','pacientes.ver'),
 ('pacientes.tab.documentos','Pacientes · pestaña Documentos','pacientes.ver'),
 ('pacientes.tab.plan-econ','Pacientes · pestaña Plan económico','pacientes.ver'),
 ('gestoria.tab.facturacion','Gestoría · pestaña Facturación','gestoria.ver'),
 ('gestoria.tab.produccion','Gestoría · pestaña Producción','gestoria.ver'),
 ('config.tab.clinica','Configuración · Clínica','config.ver'),
 ('config.tab.admin','Configuración · Admin','config.ver'),
 ('config.tab.conectores','Configuración · Conectores','config.ver'),
 ('config.tab.automatizaciones','Configuración · Automatizaciones','config.ver'),
 ('config.tab.flujos','Configuración · Flujos','config.ver'),
 ('config.tab.agentes','Configuración · Agentes IA','config.ver');

INSERT INTO permisos (created_at, updated_at, codigo, descripcion)
SELECT now(), now(), codigo, descripcion FROM _tabs
ON CONFLICT (codigo) DO NOTHING;

-- Roles que ya dan el área → dan todas sus pestañas.
INSERT INTO role_permisos (created_at, updated_at, rol_id, permiso_id)
SELECT DISTINCT now(), now(), rp.rol_id, pt.id
FROM _tabs t
JOIN permisos pa ON pa.codigo = t.area
JOIN role_permisos rp ON rp.permiso_id = pa.id
JOIN permisos pt ON pt.codigo = t.codigo
ON CONFLICT DO NOTHING;

-- Personas con el área como permiso DIRECTO → todas sus pestañas como directas.
INSERT INTO user_center_permisos (usuario_id, centro_id, permiso_id)
SELECT DISTINCT u.usuario_id, u.centro_id, pt.id
FROM _tabs t
JOIN permisos pa ON pa.codigo = t.area
JOIN user_center_permisos u ON u.permiso_id = pa.id
JOIN permisos pt ON pt.codigo = t.codigo
ON CONFLICT DO NOTHING;

-- Lo que el rol da por pestaña y la persona no tiene como directo → límite (denegado).
INSERT INTO user_center_permisos_denegados (usuario_id, centro_id, permiso_id)
SELECT DISTINCT ucr.usuario_id, ucr.centro_id, rp.permiso_id
FROM user_center_roles ucr
JOIN role_permisos rp ON rp.rol_id = ucr.rol_id
JOIN permisos p ON p.id = rp.permiso_id AND p.codigo IN (SELECT codigo FROM _tabs)
WHERE NOT EXISTS (SELECT 1 FROM user_center_permisos d
                  WHERE d.usuario_id = ucr.usuario_id AND d.centro_id = ucr.centro_id AND d.permiso_id = rp.permiso_id)
ON CONFLICT DO NOTHING;

COMMIT;
