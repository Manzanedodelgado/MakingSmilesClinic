-- 036 · Consentimientos: refuerza el enlace público de firma (signing_code).
-- 1) Amplía signing_code de varchar(16) a varchar(24): el código pasa de
--    secrets.token_urlsafe(6) (48 bits, 8 chars) a token_urlsafe(16) (128 bits, ~22 chars);
--    no se recorta el token para no perder entropía.
-- 2) Añade signing_code_expira: caducidad del enlace mientras el consentimiento esté
--    'pendiente' (30 días desde generar()); una vez 'firmado' no se comprueba, el enlace
--    sigue sirviendo en modo lectura (ver consentimiento_service.expirado()).
ALTER TABLE consentimientos ALTER COLUMN signing_code TYPE VARCHAR(24);
ALTER TABLE consentimientos ADD COLUMN IF NOT EXISTS signing_code_expira TIMESTAMP;
