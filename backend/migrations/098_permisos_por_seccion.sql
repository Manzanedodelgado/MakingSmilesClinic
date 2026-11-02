-- 098: permisos por SECCIÓN dentro de cada pestaña (Facturación, Producción, Config…).
-- Una sección solo cuenta si la persona tiene también la pestaña (<area>.tab.<x>), y esta el área.
-- SIN CAMBIO DE ACCESO HOY: quien tenía la pestaña recibe todas sus secciones; a quien el rol se las
-- daría pero tiene la pestaña denegada, se le deniegan.
BEGIN;
CREATE TEMP TABLE _subs (codigo text, descripcion text, padre text) ON COMMIT DROP;
INSERT INTO _subs VALUES
 ('gestoria.tab.facturacion.debehaber','Gestoría · Facturación · Debe / Haber','gestoria.tab.facturacion'),
 ('gestoria.tab.facturacion.facturas','Gestoría · Facturación · Facturas','gestoria.tab.facturacion'),
 ('gestoria.tab.facturacion.pagos','Gestoría · Facturación · Pagos','gestoria.tab.facturacion'),
 ('gestoria.tab.facturacion.impuestos','Gestoría · Facturación · Impuestos','gestoria.tab.facturacion'),
 ('gestoria.tab.facturacion.envio','Gestoría · Facturación · Envío','gestoria.tab.facturacion'),
 ('gestoria.tab.facturacion.historico','Gestoría · Facturación · Histórico','gestoria.tab.facturacion'),
 ('gestoria.tab.facturacion.gestor','Gestoría · Facturación · Gestor IA','gestoria.tab.facturacion'),
 ('gestoria.tab.produccion.tratamientos','Gestoría · Producción · Tratamientos','gestoria.tab.produccion'),
 ('gestoria.tab.produccion.doctores','Gestoría · Producción · Doctores','gestoria.tab.produccion'),
 ('gestoria.tab.produccion.pacientes','Gestoría · Producción · Pacientes','gestoria.tab.produccion'),
 ('config.tab.clinica.centro','Configuración · Clínica · Centro','config.tab.clinica'),
 ('config.tab.clinica.agenda','Configuración · Clínica · Agenda','config.tab.clinica'),
 ('config.tab.clinica.personal','Configuración · Clínica · Personal','config.tab.clinica'),
 ('config.tab.clinica.colaboradores','Configuración · Clínica · Colaboradores','config.tab.clinica'),
 ('config.tab.admin.diseno','Configuración · Admin · Diseño','config.tab.admin'),
 ('config.tab.admin.documentos','Configuración · Admin · Documentos','config.tab.admin'),
 ('config.tab.admin.tablas','Configuración · Admin · Tablas','config.tab.admin'),
 ('config.tab.conectores.whatsapp','Configuración · Conectores · WhatsApp','config.tab.conectores'),
 ('config.tab.conectores.voicebot','Configuración · Conectores · Voicebot','config.tab.conectores'),
 ('config.tab.conectores.mail','Configuración · Conectores · Mail','config.tab.conectores'),
 ('config.tab.conectores.drive','Configuración · Conectores · Drive','config.tab.conectores'),
 ('config.tab.conectores.radiografias','Configuración · Conectores · Radiografías','config.tab.conectores'),
 ('config.tab.conectores.servidor','Configuración · Conectores · Servidor','config.tab.conectores'),
 ('config.tab.automatizaciones.reglas','Configuración · Automatizaciones · Reglas','config.tab.automatizaciones'),
 ('config.tab.automatizaciones.editor','Configuración · Automatizaciones · Editor','config.tab.automatizaciones'),
 ('config.tab.automatizaciones.plantillas','Configuración · Automatizaciones · Plantillas','config.tab.automatizaciones'),
 ('config.tab.flujos.flujos','Configuración · Flujos · Flujos','config.tab.flujos'),
 ('config.tab.flujos.editor','Configuración · Flujos · Editor','config.tab.flujos');

INSERT INTO permisos (created_at, updated_at, codigo, descripcion)
SELECT now(), now(), codigo, descripcion FROM _subs ON CONFLICT (codigo) DO NOTHING;

INSERT INTO role_permisos (created_at, updated_at, rol_id, permiso_id)
SELECT DISTINCT now(), now(), rp.rol_id, ps.id
FROM _subs s JOIN permisos pp ON pp.codigo = s.padre
JOIN role_permisos rp ON rp.permiso_id = pp.id
JOIN permisos ps ON ps.codigo = s.codigo
ON CONFLICT DO NOTHING;

INSERT INTO user_center_permisos (usuario_id, centro_id, permiso_id)
SELECT DISTINCT u.usuario_id, u.centro_id, ps.id
FROM _subs s JOIN permisos pp ON pp.codigo = s.padre
JOIN user_center_permisos u ON u.permiso_id = pp.id
JOIN permisos ps ON ps.codigo = s.codigo
ON CONFLICT DO NOTHING;

-- Lo que el rol da por sección y la persona tiene denegado a nivel de pestaña → denegado también.
INSERT INTO user_center_permisos_denegados (usuario_id, centro_id, permiso_id)
SELECT DISTINCT ucr.usuario_id, ucr.centro_id, ps.id
FROM _subs s
JOIN permisos pp ON pp.codigo = s.padre
JOIN permisos ps ON ps.codigo = s.codigo
JOIN role_permisos rp ON rp.permiso_id = ps.id
JOIN user_center_roles ucr ON ucr.rol_id = rp.rol_id
WHERE EXISTS (SELECT 1 FROM user_center_permisos_denegados d
              WHERE d.usuario_id = ucr.usuario_id AND d.centro_id = ucr.centro_id AND d.permiso_id = pp.id)
  AND NOT EXISTS (SELECT 1 FROM user_center_permisos d
              WHERE d.usuario_id = ucr.usuario_id AND d.centro_id = ucr.centro_id AND d.permiso_id = ps.id)
ON CONFLICT DO NOTHING;
COMMIT;
