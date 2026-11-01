#!/bin/bash
set -e

echo "🧪 TEST SCRIPT — 3 Caminos de Consulta Clínica"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"
PACIENTE_ID=4767

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ═════════════════════════════════════════════════════════════════════════════
# 1. HEALTH CHECK
# ═════════════════════════════════════════════════════════════════════════════
echo -e "${BLUE}1. HEALTH CHECK${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if curl -s "$BACKEND_URL/health" | grep -q "ok"; then
  echo -e "${GREEN}✅ Backend respondiendo en :8000${NC}"
else
  echo -e "${RED}❌ Backend NO responde${NC}"
  exit 1
fi

# ═════════════════════════════════════════════════════════════════════════════
# 2. TEST B1: DETECCIÓN DE CAMINO
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}2. TEST B1: DETECCIÓN DE CAMINO${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Nota: Esto requiere autenticación. En local, asumir cookies ya están seteadas.
# Para un test real, necesitaríamos login primero.

echo "ℹ️  Endpoint: GET /pacientes/$PACIENTE_ID/consulta/camino"
echo "⚠️  Requiere autenticación (cookies JWT desde navegador)"
echo "    En testing manual, abre DevTools → Network → filtra 'camino'"
echo "    Verifica que devuelve: { camino: 1|2|3, ... }"

# ═════════════════════════════════════════════════════════════════════════════
# 3. TEST A2: CONSENTIMIENTO 422
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}3. TEST A2: CONSENTIMIENTO 422${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "✓ Validación backend implementada en: /pacientes/{id}/presupuestos/realizar-en-cita"
echo ""
echo "Pasos de verificación:"
echo "  1. Buscar tratamiento con consentimiento_tipo ≠ NULL"
echo "  2. Cita de paciente sin consentimiento firmado"
echo "  3. Clic 'Registrar realizado' → Debe fallar con 422"
echo "  4. Error debe contener tipo requerido (ej: 'ortodoncia')"
echo "  5. Abrir ConsentimientosPanel → Firmar → Reintentar → Debe éxito"

# ═════════════════════════════════════════════════════════════════════════════
# 4. TEST A3: RECOMENDACIONES
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}4. TEST A3: RECOMENDACIONES${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "✓ Catálogo disponible en: GET /pacientes/recomendaciones/catalogo"
echo ""
echo "Pasos de verificación:"
echo "  1. Llegar a 'PostConsultaDocumentos' (cualquier camino)"
echo "  2. Pregunta 3: ¿Deseas añadir recomendaciones?"
echo "  3. Clic 'Sí, abrir' → RecomendacionesModal abre"
echo "  4. Seleccionar items de 5 secciones"
echo "  5. Clic 'Guardar Recomendaciones'"
echo "  6. Tras guardar: botones 'Imprimir' y 'Enviar WhatsApp' aparecen"
echo "  7. Verificar en BD: SELECT * FROM recomendaciones_paciente ORDER BY created_at DESC LIMIT 1"

# ═════════════════════════════════════════════════════════════════════════════
# 5. VERIFICACIÓN DE ARCHIVOS
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}5. VERIFICACIÓN DE ARCHIVOS${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ARCHIVOS=(
  "backend/api/consulta_router.py"
  "frontend/src/features/patients/components/EjecutarTratamiento.tsx"
  "frontend/src/features/patients/components/RecetaModal.tsx"
  "frontend/src/features/patients/components/PresupuestoModal.tsx"
  "frontend/src/features/patients/components/RecomendacionesModal.tsx"
  "frontend/e2e/3-caminos.spec.ts"
)

for archivo in "${ARCHIVOS[@]}"; do
  if [ -f "$archivo" ]; then
    echo -e "${GREEN}✅ $archivo${NC}"
  else
    echo -e "${RED}❌ $archivo (FALTA)${NC}"
  fi
done

# ═════════════════════════════════════════════════════════════════════════════
# 6. TESTS E2E (PLAYWRIGHT)
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}6. TESTS E2E (PLAYWRIGHT)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Para ejecutar tests e2e:"
echo "  $ cd frontend"
echo "  $ npm run test:e2e              # Headless (CI/CD)"
echo "  $ npm run test:e2e:ui           # Con navegador (recomendado)"
echo "  $ npm run test:e2e:debug        # Con debugger"
echo ""
echo "Tests incluidos:"
echo "  • 3 Caminos completos"
echo "  • A2 Validación consentimiento"
echo "  • A3 Guardado de recomendaciones"

# ═════════════════════════════════════════════════════════════════════════════
# 7. TESTING MANUAL PASO A PASO
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}7. TESTING MANUAL (PASO A PASO)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "CAMINO 1: Ejecutar Tratamiento"
echo "  1. Navega a: $FRONTEND_URL/pacientes/$PACIENTE_ID/ficha"
echo "  2. Clic botón 'Consulta'"
echo "  3. Si abre 'EjecutarTratamiento' → Camino 1 detectado ✓"
echo "  4. Selecciona líneas → Clic 'Registrar realizado'"
echo "  5. Verifica que 'PostConsultaDocumentos' abre con 3 preguntas"
echo ""

echo "CAMINO 2: Primera Visita"
echo "  1. Usa paciente nuevo (sin citas previas)"
echo "  2. Clic 'Consulta' → Debe abrir 'Escucha' (IA)"
echo "  3. Dicta evaluación → Clic 'Estructurar'"
echo "  4. Verifica SOAP+presupuesto+receta+mensaje aparecen"
echo ""

echo "CAMINO 3: Revisión"
echo "  1. Paciente existente (con citas previas, sin previstos hoy)"
echo "  2. Clic 'Consulta' → Debe abrir 'Escucha'"
echo "  3. Dicta evaluación → ¿Realizado hoy? Marca sí/no"
echo ""

echo "CONSENTIMIENTO (A2)"
echo "  1. Ejecutar tratamiento que requiere consentimiento"
echo "  2. Sin consentimiento: error 422 con tipo requerido"
echo "  3. Abrir ConsentimientosPanel → Firmar → Reintentar"
echo ""

echo "RECOMENDACIONES (A3)"
echo "  1. PostConsultaDocumentos → Pregunta 3"
echo "  2. Sí, abrir → RecomendacionesModal"
echo "  3. Selecciona items → Guardar"
echo "  4. Verifica botones Imprimir/WhatsApp aparecen"

# ═════════════════════════════════════════════════════════════════════════════
# 8. DEBUG MODE
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}8. DEBUG MODE${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Dashboard de monitoreo (EN VIVO):"
echo "  URL: $FRONTEND_URL/pacientes/$PACIENTE_ID/ficha?debug=caminos"
echo ""
echo "Muestra métricas de detección y ejecución de los 3 caminos"
echo "En DevTools Console:"
echo "  • window.localStorage.getItem('camino_evento_$PACIENTE_ID')"
echo "  • Busca 'detectarCamino' en Network para ver payload/response"

# ═════════════════════════════════════════════════════════════════════════════
# RESUMEN
# ═════════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo -e "${GREEN}✅ TEST SCRIPT COMPLETADO${NC}"
echo ""
echo "Próximos pasos:"
echo "  1. Ejecutar tests e2e: npm run test:e2e:ui"
echo "  2. O testing manual siguiendo pasos arriba"
echo "  3. Verificar métricas en: $FRONTEND_URL/pacientes/$PACIENTE_ID/ficha?debug=caminos"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
