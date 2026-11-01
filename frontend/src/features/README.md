# Estructura feature-first

Cada funcionalidad de la plataforma vivirá en su propia carpeta dentro de
`src/features/`, manteniendo juntos los componentes, hooks, servicios y tipos
que le pertenecen.

Funcionalidades previstas:

- `agenda` — gestión de citas y horarios.
- `auth` — autenticación y sesión (se implementará en el milestone M01).
- `patients` — fichas y datos de pacientes.
- `comunicacion` — mensajería y notificaciones.
- `gestoria` — documentación y trámites.

Convenciones:

- Cada feature expone su UI pública a través de un `index.ts`.
- El estado y la lógica específicos de la feature no se comparten entre features.
- El código compartido transversal vive en `src/shared/` (por crear).
