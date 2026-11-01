#!/bin/bash
# Deploy backend con gate patches-to-core previo.
# Uso: bash scripts/deploy-backend.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# Candado: un solo despliegue a la vez y constancia de qué entra (ver scripts/deploy-lock.sh).
source scripts/deploy-lock.sh "deploy-backend"

# Gate: bloquea si el diff mete parches sin trazar o fallan los tests del área.
bash scripts/deploy-gate.sh

echo "Gate superado. Levantando backend + redis + postgres + evolution…"
docker compose -f docker-compose.yml up -d --build backend redis postgres evolution
docker compose -f docker-compose.yml ps backend
