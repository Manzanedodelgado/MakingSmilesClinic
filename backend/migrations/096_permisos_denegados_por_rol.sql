-- 096: límites de permisos por persona sobre el rol.
--
-- Modelo nuevo: efectivos = (permisos del rol − denegados de la persona) ∪ directos.
-- El rol marca el techo; user_center_permisos_denegados quita permisos concretos a UNA
-- persona sin tocar el rol. Los directos (user_center_permisos) se mantienen como excepciones
-- heredadas hasta que se reasignen a mano.
--
-- MIGRACIÓN DE DATOS SIN CAMBIO DE ACCESO: hasta hoy el rol NO daba permisos (solo los
-- directos). Para que nadie gane acceso al activar el rol, cada persona recibe como
-- "denegados" todo lo que su rol concede y que no tiene ya como permiso directo.
-- Efectivos antes = directos; efectivos después = directos ∪ (rol − denegados) = directos.
BEGIN;

CREATE TABLE IF NOT EXISTS user_center_permisos_denegados (
    created_at timestamp NOT NULL DEFAULT now(),
    updated_at timestamp NOT NULL DEFAULT now(),
    usuario_id integer NOT NULL REFERENCES usuarios(id),
    centro_id  integer NOT NULL REFERENCES centros(id),
    permiso_id integer NOT NULL REFERENCES permisos(id),
    PRIMARY KEY (usuario_id, centro_id, permiso_id)
);
CREATE INDEX IF NOT EXISTS ix_ucpd_usuario ON user_center_permisos_denegados (usuario_id);
CREATE INDEX IF NOT EXISTS ix_ucpd_centro  ON user_center_permisos_denegados (centro_id);
CREATE INDEX IF NOT EXISTS ix_ucpd_permiso ON user_center_permisos_denegados (permiso_id);

INSERT INTO user_center_permisos_denegados (usuario_id, centro_id, permiso_id)
SELECT DISTINCT ucr.usuario_id, ucr.centro_id, rp.permiso_id
FROM user_center_roles ucr
JOIN role_permisos rp ON rp.rol_id = ucr.rol_id
JOIN permisos p ON p.id = rp.permiso_id AND p.codigo <> 'superuser'
WHERE NOT EXISTS (
    SELECT 1 FROM user_center_permisos ucp
    WHERE ucp.usuario_id = ucr.usuario_id AND ucp.centro_id = ucr.centro_id AND ucp.permiso_id = rp.permiso_id
)
ON CONFLICT DO NOTHING;

COMMIT;
