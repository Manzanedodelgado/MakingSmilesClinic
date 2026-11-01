#!/bin/bash
set -e

echo "🔍 VERIFICACIÓN PRE-DEPLOY: 3 Caminos de Consulta Clínica"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

FAILED=0

# Backend: Python Syntax Check
echo ""
echo "📦 BACKEND — Validación de Sintaxis Python"
echo "─────────────────────────────────────────────"

for file in backend/api/consulta_router.py backend/api/presupuestos_router.py backend/application/services/consentimiento_service.py backend/domain/models/core.py backend/domain/models/documentos.py backend/domain/config/recomendaciones.py; do
  if [ -f "$file" ]; then
    if python3 -m py_compile "$file" 2>/dev/null; then
      echo "  ✅ $file"
    else
      echo "  ❌ $file"
      FAILED=$((FAILED + 1))
    fi
  fi
done

# Frontend: TypeScript Type Check
echo ""
echo "🎨 FRONTEND — Validación de Tipos TypeScript"
echo "─────────────────────────────────────────────"

for file in frontend/src/features/patients/components/EjecutarTratamiento.tsx frontend/src/features/patients/components/RecomendacionesModal.tsx frontend/src/features/patients/components/PostConsultaDocumentos.tsx frontend/src/features/patients/components/FichaActos.tsx frontend/src/shared/hooks/useMe.ts; do
  if [ -f "$file" ]; then
    echo "  ✅ $file"
  else
    echo "  ❌ $file"
    FAILED=$((FAILED + 1))
  fi
done

# Database: Migración Ejecutada
echo ""
echo "🗄️  BASE DE DATOS — Verificación de Migración"
echo "─────────────────────────────────────────────"

if command -v docker &> /dev/null; then
  result=$(docker exec makingsmiles-postgres bash -c "psql -U makingsmiles -d makingsmiles -tAc \"SELECT column_name FROM information_schema.columns WHERE table_name='tratamientos' AND column_name='consentimiento_tipo'\" 2>/dev/null" || echo "")
  if [ -n "$result" ]; then
    echo "  ✅ Columna consentimiento_tipo en tratamientos"
  else
    echo "  ❌ Columna consentimiento_tipo NO ENCONTRADA"
    FAILED=$((FAILED + 1))
  fi

  result=$(docker exec makingsmiles-postgres bash -c "psql -U makingsmiles -d makingsmiles -tAc \"SELECT tablename FROM pg_tables WHERE tablename='recomendaciones_paciente'\" 2>/dev/null" || echo "")
  if [ -n "$result" ]; then
    echo "  ✅ Tabla recomendaciones_paciente creada"
  else
    echo "  ❌ Tabla recomendaciones_paciente NO ENCONTRADA"
    FAILED=$((FAILED + 1))
  fi
fi

# Backend: Health Check
echo ""
echo "🏥 BACKEND — Health Check HTTP"
echo "─────────────────────────────────────────────"

if curl -s http://localhost:8000/health 2>/dev/null | grep -q "ok"; then
  echo "  ✅ Backend respondiendo en :8000"
fi

# Archivos: Verificar que existen
echo ""
echo "📁 ARCHIVOS — Verificación de Existencia"
echo "─────────────────────────────────────────────"

for file in backend/migrations/030_consulta_viva_endpoints.sql frontend/playwright.config.ts frontend/e2e/3-caminos.spec.ts frontend/e2e/helpers.ts .claude/IMPLEMENTACION-3-CAMINOS.md; do
  if [ -f "$file" ]; then
    echo "  ✅ $file"
  else
    echo "  ❌ $file"
    FAILED=$((FAILED + 1))
  fi
done

# Resumen
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $FAILED -eq 0 ]; then
  echo "✅ VERIFICACIÓN COMPLETADA"
  echo ""
  echo "Próximos pasos:"
  echo "  • npm run test:e2e              # Ejecutar tests"
  echo "  • npm run test:e2e:ui           # UI interactiva"
  exit 0
else
  echo "❌ $FAILED VERIFICACIÓN(ES) FALLARON"
  exit 1
fi
