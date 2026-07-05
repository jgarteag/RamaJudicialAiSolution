# ============================================
# Root Module - Orquestador Microstack Frontend
# Compone S3 + CloudFront para hosting estático
# ============================================

# Sufijo único para evitar colisiones de nombres S3
resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  suffix = random_id.suffix.hex
  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# --------------------------------------------
# CloudFront Distribution
# Se crea primero porque S3 necesita su ARN
# --------------------------------------------
module "cloudfront" {
  source = "./modules/cloudfront"

  project_name                   = var.project_name
  environment                    = var.environment
  s3_bucket_regional_domain_name = module.s3_frontend.bucket_regional_domain_name
  price_class                    = var.cloudfront_price_class
  tags                           = local.tags
}

# --------------------------------------------
# S3 Bucket - Frontend hosting
# --------------------------------------------
module "s3_frontend" {
  source = "./modules/s3-frontend"

  project_name                = var.project_name
  environment                 = var.environment
  suffix                      = local.suffix
  cloudfront_distribution_arn = module.cloudfront.distribution_arn
  tags                        = local.tags
}
