-- 037 · Recetas: casillas "Urgencia"/"Desabastecimiento" del PDF oficial de receta médica
-- privada (información al farmacéutico). El resto de campos del PDF ya existen
-- (notas = instrucciones al paciente, notas_farmaceutico = motivo de la sustitución,
-- diagnostico, archivo_url para el PDF generado).
ALTER TABLE recetas ADD COLUMN IF NOT EXISTS urgencia BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE recetas ADD COLUMN IF NOT EXISTS desabastecimiento BOOLEAN NOT NULL DEFAULT FALSE;
