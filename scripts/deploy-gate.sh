#!/bin/bash
# Gate patches-to-core: se ejecuta antes de cada deploy.
# 1) Escanea marcadores de parche sin trazar + except silenciosos en 3 fuentes.
# 2) Corre los tests del área afectada.
# Bloquea (exit 1) ante cualquier fallo. Nunca aprueba por silencio.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 0/2 .env completo =="
# Incidente 18/19-oct-2026: el .env se sobrescribió con 7 de sus 42 variables y el
# backend se desplegó sin claves de IA, WhatsApp, IMAP, cifrado ni destino de copias.
# Sin estas variables no se despliega (solo se comprueba que existan y no estén vacías).
ENV_OBLIGATORIAS="DATABASE_URL SECRET_KEY BACKUP_DESTINO CIFRADO_CREDENCIALES_KEY EVOLUTION_API_KEY IMAP_HOST IMAP_USER IMAP_PASSWORD GEMINI_API_KEY NVIDIA_API_KEY OPENROUTER_API_KEY GOOGLE_SERVICE_ACCOUNT_JSON"
FALTAN_ENV=""
for v in $ENV_OBLIGATORIAS; do
  grep -qE "^${v}=.+" .env 2>/dev/null || FALTAN_ENV="$FALTAN_ENV $v"
done
if [ -n "$FALTAN_ENV" ]; then
  echo "BLOQUEO: faltan o están vacías en .env:$FALTAN_ENV"
  echo "         Recupera el .env de la última copia (servidor.tar.gz → servidor/env) en BACKUP_DESTINO."
  exit 1
fi
echo "OK: .env con todas las variables obligatorias."

BASE="${1:-}"
if [ -z "$BASE" ]; then
  # Rama base real del repo (master), no un nombre supuesto.
  BASE="origin/$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p')"
  [ "$BASE" = "origin/" ] && BASE="origin/master"
fi
if ! git rev-parse --verify "$BASE" >/dev/null 2>&1; then
  echo "BLOQUEO: no existe la rama base '$BASE' (haz fetch antes del deploy)."
  exit 1
fi
echo "== patches-to-core gate: diff vs $BASE =="
DIFF_STAT=$(git diff --stat "$BASE"...HEAD 2>/dev/null || git diff --stat)
echo "$DIFF_STAT" | tail -n 5

echo "== 1/2 escaneo de marcadores + except silenciosos =="
# Tres fuentes (el deploy debe verse libre vengas de donde vengas):
#   A) diff commiteado vs base, B) cambios sin commitear (staged+unstaged),
#   C) ficheros .py nuevos sin trackear (no salen en ningún diff).
# Se excluyen el propio gate, el helper, la doc de la skill, .venv, node_modules y tests.
EXCL=':!scripts/deploy-gate.sh' && EXCL2=':!scripts/check-silent-except.py'
SKILL=':!.agents/skills/patches-to-core/SKILL.md' && DOCS=':!docs'
# Tooling y skills de terceros: no es código de producto, no se escanea.
TOOL=':!.claude :!.github :!.gstack :!.impeccable :!.serena :!frontend/.next :!frontend/.next-prod :!frontend/.next-audit :!frontend/out :!frontend/dist :!frontend/build'
set -- "$EXCL" "$EXCL2" "$SKILL" "$DOCS" $TOOL
HALLAZGOS=""
HALLAZGOS="$HALLAZGOS"$'\n'$(git diff "$BASE"...HEAD -- . "$@" ':!backend/.venv' ':!backend/tests' 2>/dev/null | python3 scripts/check-silent-except.py --diff || echo "ERROR-LECTURA-DIFF-A")
HALLAZGOS="$HALLAZGOS"$'\n'$(git diff HEAD -- . "$@" ':!backend/.venv' ':!backend/tests' 2>/dev/null | python3 scripts/check-silent-except.py --diff || echo "ERROR-LECTURA-DIFF-B")
HALLAZGOS="$HALLAZGOS"$'\n'$(git ls-files --others --exclude-standard -- '*.py' '*.ts' '*.tsx' '*.js' '*.swift' 2>/dev/null | { grep -v -E "^\.venv|/\.venv/|node_modules|/tests/|backend/tests/|^scripts/check-silent-except\.py|^\.claude/|^.github/|^.gstack/|^.impeccable/|^.serena/" || true; } | python3 scripts/check-silent-except.py --files || echo "ERROR-LECTURA-FILES-C")
if echo "$HALLAZGOS" | grep -q "ERROR-LECTURA"; then
  echo "BLOQUEO: el gate no pudo leer alguna fuente (fallo, no aprobación):"
  echo "$HALLAZGOS" | grep "ERROR-LECTURA"
  exit 1
fi
if [ -n "$(echo "$HALLAZGOS" | tr -d '[:space:]')" ]; then
  echo "BLOQUEO: parches sin trazar (añade logger/documenta el fallback o traza el marcador):"
  echo "$HALLAZGOS"
  exit 1
fi
echo "OK: sin marcadores ni except silenciosos (commiteado + sin commitear + nuevos)."

echo "== 1b/2 envoltorios sobre raíz intacta (BLOQUEA hasta resolverse en raíz) =="
ENVOLTORIOS=""
ENVOLTORIOS="$ENVOLTORIOS"$'\n'$(git diff "$BASE"...HEAD -- . "$@" ':!backend/.venv' ':!backend/tests' 2>/dev/null | python3 scripts/check-silent-except.py --envoltorios || echo "ERROR-ENV-A")
ENVOLTORIOS="$ENVOLTORIOS"$'\n'$(git diff HEAD -- . "$@" ':!backend/.venv' ':!backend/tests' 2>/dev/null | python3 scripts/check-silent-except.py --envoltorios || echo "ERROR-ENV-B")
ENVOLTORIOS=$(echo "$ENVOLTORIOS" | grep -v "^$" || true)
if echo "$ENVOLTORIOS" | grep -q "ERROR-ENV"; then
  echo "BLOQUEO: el gate no pudo leer envoltorios (fallo, no aprobación)."
  exit 1
fi
if [ -n "$ENVOLTORIOS" ]; then
  echo "BLOQUEO: código nuevo que envuelve raíz intacta — resolver en la raíz:"
  echo "$ENVOLTORIOS"
  exit 1
fi
echo "OK: sin envoltorios sobre raíz intacta."

echo "== 1b/2 sospechosos (heurística: se LISTAN, los decide un humano) =="
# except/catch genérico, IPs duras, as-any/eslint-disable, try?, esperas mágicas.
# Solo código NUEVO (diffs + untracked): el legado ya está inventariado, no bloquea.
SOSPECHOSOS=""
SOSPECHOSOS="$SOSPECHOSOS"$'\n'$(git diff "$BASE"...HEAD -- . "$@" ':!backend/.venv' ':!backend/tests' 2>/dev/null | python3 scripts/check-silent-except.py --diff --sospechosos || echo "ERROR-SUSP-A")
SOSPECHOSOS="$SOSPECHOSOS"$'\n'$(git diff HEAD -- . "$@" ':!backend/.venv' ':!backend/tests' 2>/dev/null | python3 scripts/check-silent-except.py --diff --sospechosos || echo "ERROR-SUSP-B")
SOSPECHOSOS="$SOSPECHOSOS"$'\n'$(git ls-files --others --exclude-standard -- '*.py' '*.ts' '*.tsx' '*.js' '*.swift' 2>/dev/null | { grep -v -E "^\.venv|/\.venv/|node_modules|/tests/|backend/tests/|^scripts/check-silent-except\.py|^\.claude/|^.github/|^.gstack/|^.impeccable/|^.serena/" || true; } | python3 scripts/check-silent-except.py --files --sospechosos || echo "ERROR-SUSP-C")
SOSPECHOSOS=$(echo "$SOSPECHOSOS" | grep -v "^$" || true)
if echo "$SOSPECHOSOS" | grep -q "ERROR-SUSP"; then
  echo "BLOQUEO: el gate no pudo leer sospechosos (fallo, no aprobación)."
  exit 1
fi
if [ -n "$SOSPECHOSOS" ]; then
  echo "AVISO: sospechosos en código nuevo (no bloquea; revisar antes de desplegar):"
  echo "$SOSPECHOSOS" | head -n 30
else
  echo "OK: sin sospechosos en código nuevo."
fi

echo "== 1c/3 un solo dueño por entidad (BLOQUEA) =="
if ! python3 scripts/check-un-solo-dueno.py; then
  echo "BLOQUEO: hay una entidad que se escribe desde dos sitios."
  exit 1
fi

echo "== 2/3 tests del área afectada =="
CAMBIOS=$(git diff --name-only "$BASE"...HEAD 2>/dev/null || git diff --name-only)
if echo "$CAMBIOS" | grep -q "consentimiento"; then
  python3 -m pytest backend/tests/test_consentimientos.py -q 2>&1 | tail -n 3
fi
if echo "$CAMBIOS" | grep -qE "comunicacion|automatizacion|evolution|whatsapp"; then
  python3 -m pytest backend/tests/ -q -k "comunicacion or conversa or whatsapp or automatizacion" 2>&1 | tail -n 3
fi
echo "Gate superado (o sin tests específicos para el área; el resto de flujos se barren por turno)."
