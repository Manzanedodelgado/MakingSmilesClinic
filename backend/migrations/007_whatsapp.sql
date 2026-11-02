-- 007 · WhatsApp / Comunicación: portar el módulo de WhatsApp de la .37 a la
--   BBDD nueva. Mapeo verificado en docs (whatsapp .37 → MakingSmiles).
--   Principio: cero duplicación. La conversación y el mensaje YA viven en
--   `conversaciones`/`mensajes` (versión mínima); aquí solo ampliamos lo que
--   faltaba para operar con Evolution API (dedup por message_id, estado de
--   entrega, media, citas/respuestas) y añadimos plantillas y encuestas.
--
--   Decisiones de estructura (no arrastramos bugs de la .37):
--     · Dedup REAL por message_id con índice UNIQUE → INSERT ... ON CONFLICT.
--     · Multi-tenant: las credenciales Evolution viven en `integraciones`
--       (tipo='whatsapp', config JSON) por centro. NADA hardcodeado.
--     · Pausa de IA por conversación → en `configuraciones` (no tabla propia).

-- ── A) CONVERSACIONES: bandeja (no leídos, último mensaje, archivado, fijado) ──
ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS no_leidos          INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS ultimo_mensaje     VARCHAR(200);
ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS ultimo_mensaje_at  TIMESTAMP WITHOUT TIME ZONE;
ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS archivada          BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE conversaciones ADD COLUMN IF NOT EXISTS mensaje_fijado_id  INTEGER;
-- Una conversación por canal+teléfono dentro del centro (getOrCreate atómico).
CREATE UNIQUE INDEX IF NOT EXISTS uq_conversacion_centro_canal_tel
    ON conversaciones (centro_id, canal, telefono) WHERE telefono IS NOT NULL;

-- ── B) MENSAJES: dedup Evolution, estado de entrega, media y respuestas ───────
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS message_id      VARCHAR(160);  -- id de Evolution
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS estado          VARCHAR(20) NOT NULL DEFAULT 'enviado';
                                              -- pendiente | enviado | entregado | leido | error
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS media_url       VARCHAR(500);
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS media_tipo      VARCHAR(40);   -- image|video|audio|document
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS media_nombre    VARCHAR(255);
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS responde_a_id   VARCHAR(160);  -- message_id citado
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS responde_a_texto VARCHAR(500);
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS fijado          BOOLEAN NOT NULL DEFAULT FALSE;
-- Dedup ATÓMICO: el id de Evolution es único. El eco del webhook y el envío
-- propio comparten message_id; la 2ª inserción cae en ON CONFLICT DO NOTHING.
CREATE UNIQUE INDEX IF NOT EXISTS uq_mensajes_message_id
    ON mensajes (message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_mensajes_estado ON mensajes (estado);

-- ── C) PLANTILLAS DE MENSAJE (whatsapp_message_templates) ─────────────────────
--   Editables por el centro = CONFIG es la fuente de la verdad (nada hardcodeado).
--   tipo: texto | encuesta(poll) | lista. `opciones` = JSON [{etiqueta, accion}].
CREATE TABLE IF NOT EXISTS plantillas_mensaje (
  id            SERIAL PRIMARY KEY,
  created_at    TIMESTAMP WITHOUT TIME ZONE,
  updated_at    TIMESTAMP WITHOUT TIME ZONE,
  centro_id     INTEGER NOT NULL REFERENCES centros(id),
  disparador    VARCHAR(60),                 -- recordatorio_24h, cita_confirmada…
  nombre        VARCHAR(120)  NOT NULL,
  cuerpo        VARCHAR(4000) NOT NULL,      -- con variables {{nombre}} {{fecha}} {{hora}}…
  tipo          VARCHAR(20)   NOT NULL DEFAULT 'texto',
  opciones      JSONB,
  activo        BOOLEAN NOT NULL DEFAULT TRUE,
  updated_by    INTEGER REFERENCES usuarios(id),
  CONSTRAINT uq_plantilla_centro_disparador UNIQUE (centro_id, disparador)
);
CREATE INDEX IF NOT EXISTS ix_plantilla_centro     ON plantillas_mensaje (centro_id);
CREATE INDEX IF NOT EXISTS ix_plantilla_disparador ON plantillas_mensaje (disparador);

-- ── D) CONTEXTO DE ENCUESTAS (whatsapp_poll_context) ─────────────────────────
--   Resuelve el voto cifrado de una encuesta: guarda los hashes de cada opción
--   para mapear el voto entrante → acción. Claim atómico vía resuelto_at.
CREATE TABLE IF NOT EXISTS poll_contexto (
  id              SERIAL PRIMARY KEY,
  created_at      TIMESTAMP WITHOUT TIME ZONE,
  updated_at      TIMESTAMP WITHOUT TIME ZONE,
  centro_id       INTEGER NOT NULL REFERENCES centros(id),
  message_id      VARCHAR(160) NOT NULL,     -- id del mensaje-encuesta de Evolution
  plantilla_id    INTEGER REFERENCES plantillas_mensaje(id),
  telefono        VARCHAR(50)  NOT NULL,
  opciones        JSONB,                     -- [{etiqueta, accion}]
  opcion_hashes   JSONB,                     -- {sha256(etiqueta): indice}
  opcion_resuelta VARCHAR(200),
  resuelto_at     TIMESTAMP WITHOUT TIME ZONE,
  CONSTRAINT uq_poll_message UNIQUE (message_id)
);
CREATE INDEX IF NOT EXISTS ix_poll_centro ON poll_contexto (centro_id);

-- ── E) ACCIONES DE BOTÓN/ENCUESTA (whatsapp_button_actions) ──────────────────
--   Catálogo de qué hace cada opción: confirmar_cita, cancelar_cita,
--   reprogramar, escalar_humano, abrir_url, registrar_evento…
CREATE TABLE IF NOT EXISTS acciones_boton (
  id          SERIAL PRIMARY KEY,
  created_at  TIMESTAMP WITHOUT TIME ZONE,
  updated_at  TIMESTAMP WITHOUT TIME ZONE,
  centro_id   INTEGER REFERENCES centros(id),
  codigo      VARCHAR(60)  NOT NULL,         -- confirmar_cita | cancelar_cita | …
  etiqueta    VARCHAR(120) NOT NULL,
  descripcion VARCHAR(300),
  handler     VARCHAR(120),
  activo      BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_accion_centro ON acciones_boton (centro_id);
