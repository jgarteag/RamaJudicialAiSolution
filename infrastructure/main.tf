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

# ============================================
# Microstack 2 - Backend API (Lambda + API Gateway)
# ============================================

# --------------------------------------------
# Lambda Function - API Handler
# --------------------------------------------
module "lambda_api" {
  source = "./modules/lambda"

  project_name  = var.project_name
  environment   = var.environment
  function_name = "api"
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  memory_size   = 256
  timeout       = 30
  source_path   = "${path.module}/../backend/lambda/lambda.zip"

  enable_bedrock = true

  environment_variables = {
    ENVIRONMENT  = var.environment
    PROJECT      = var.project_name
    BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    AWS_BEDROCK_REGION = "us-east-1"
  }

  tags = local.tags
}

# --------------------------------------------
# API Gateway HTTP API (v2) - Low Cost
# --------------------------------------------
module "api_gateway" {
  source = "./modules/api-gateway"

  project_name         = var.project_name
  environment          = var.environment
  lambda_invoke_arn    = module.lambda_api.invoke_arn
  lambda_function_name = module.lambda_api.function_name

  allowed_origins = [
    "https://${module.cloudfront.distribution_domain_name}",
    "http://localhost:3000",
    "http://localhost:5500"
  ]

  tags = local.tags
}
