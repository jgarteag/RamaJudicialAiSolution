#!/usr/bin/env bash
# ============================================
# Redeploy - Orquestador general de deploys
# Ejecutado por CD (GitHub Actions) o manualmente
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Iniciando deploy de RamaJudicialAiSolution..."

# Microstack 1: Frontend (S3 + CloudFront)
echo "--- Microstack 1: Frontend ---"
"$SCRIPT_DIR/deploy-frontend.sh"

echo ""
echo "✅ Todos los microstacks desplegados exitosamente"
