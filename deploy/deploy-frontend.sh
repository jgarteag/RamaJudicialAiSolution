#!/usr/bin/env bash
# ============================================
# Deploy Frontend - Upload a S3 + Invalidate CloudFront
# Uso: ./deploy/deploy-frontend.sh
# En local usa AWS_PROFILE; en CI/CD usa OIDC credentials
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INFRA_DIR="$PROJECT_ROOT/infrastructure"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1" >&2; exit 1; }

# --------------------------------------------
# Validaciones
# --------------------------------------------
command -v aws >/dev/null 2>&1 || error "AWS CLI no instalado"
command -v terraform >/dev/null 2>&1 || error "Terraform no instalado"

[ -d "$FRONTEND_DIR" ] || error "Directorio frontend/ no encontrado"

# Detectar profile de AWS (local vs CI/CD)
AWS_ARGS=""
if [ -n "${AWS_PROFILE:-}" ]; then
  AWS_ARGS="--profile $AWS_PROFILE"
  log "Usando AWS profile: $AWS_PROFILE"
elif [ -f "$INFRA_DIR/terraform.tfvars" ]; then
  PROFILE=$(grep 'aws_profile' "$INFRA_DIR/terraform.tfvars" 2>/dev/null | sed 's/.*=\s*"\(.*\)"/\1/' | tr -d ' ')
  if [ -n "$PROFILE" ] && [ "$PROFILE" != "null" ]; then
    AWS_ARGS="--profile $PROFILE"
    log "Usando AWS profile desde tfvars: $PROFILE"
  fi
fi

# --------------------------------------------
# Obtener outputs de Terraform
# --------------------------------------------
log "Obteniendo configuración de Terraform..."
cd "$INFRA_DIR"

BUCKET_ID=$(terraform output -raw s3_bucket_id 2>/dev/null) || error "No se pudo obtener s3_bucket_id. ¿Ejecutaste terraform apply?"
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id 2>/dev/null) || error "No se pudo obtener cloudfront_distribution_id"

log "Bucket: $BUCKET_ID"
log "Distribution: $DISTRIBUTION_ID"

# --------------------------------------------
# Sync frontend a S3
# --------------------------------------------
log "Subiendo frontend a S3..."

# HTML - sin cache (siempre fresco)
aws s3 cp "$FRONTEND_DIR/index.html" "s3://$BUCKET_ID/index.html" \
  --content-type "text/html; charset=utf-8" \
  --cache-control "no-cache, no-store, must-revalidate" \
  $AWS_ARGS --quiet

# CSS - cache largo
aws s3 sync "$FRONTEND_DIR" "s3://$BUCKET_ID" \
  --exclude "*" \
  --include "*.css" \
  --content-type "text/css" \
  --cache-control "public, max-age=31536000, immutable" \
  $AWS_ARGS --quiet

# JS - cache largo
aws s3 sync "$FRONTEND_DIR" "s3://$BUCKET_ID" \
  --exclude "*" \
  --include "*.js" \
  --content-type "application/javascript" \
  --cache-control "public, max-age=31536000, immutable" \
  $AWS_ARGS --quiet

# Otros archivos estáticos (imágenes, favicons, etc.)
aws s3 sync "$FRONTEND_DIR" "s3://$BUCKET_ID" \
  --exclude "*.html" \
  --exclude "*.css" \
  --exclude "*.js" \
  --cache-control "public, max-age=86400" \
  $AWS_ARGS --quiet

log "Frontend subido exitosamente"

# --------------------------------------------
# Invalidar cache de CloudFront
# --------------------------------------------
log "Invalidando cache de CloudFront..."

INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" \
  --query 'Invalidation.Id' \
  --output text \
  $AWS_ARGS)

log "Invalidación creada: $INVALIDATION_ID"
warn "La propagación puede tomar 1-2 minutos"

# --------------------------------------------
# URL del sitio
# --------------------------------------------
DOMAIN=$(terraform output -raw cloudfront_domain 2>/dev/null)
echo ""
log "🚀 Deploy completado!"
log "URL: https://$DOMAIN"
