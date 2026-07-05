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
# DynamoDB - Agent Configuration Store
# --------------------------------------------
module "dynamodb_config" {
  source = "./modules/dynamodb"

  project_name = var.project_name
  environment  = var.environment
  tags         = local.tags
}

# --------------------------------------------
# Secrets Manager - MongoDB Connection String
# --------------------------------------------
module "secret_mongodb" {
  source = "./modules/secrets"

  project_name = var.project_name
  environment  = var.environment
  secret_name  = "mongodb-uri"
  description  = "MongoDB Atlas connection string for judicial data"
  tags         = local.tags
}

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

  layer_source_path = "${path.module}/../backend/layers/layer.zip"

  enable_bedrock     = true
  enable_dynamodb    = true
  dynamodb_table_arn = module.dynamodb_config.table_arn
  enable_secrets     = true
  secrets_arns       = [module.secret_mongodb.secret_arn]

  environment_variables = {
    ENVIRONMENT         = var.environment
    PROJECT             = var.project_name
    AGENT_ID            = "rama-judicial-ai"
    AGENT_CONFIG_TABLE  = module.dynamodb_config.table_name
    MONGODB_SECRET_NAME = module.secret_mongodb.secret_name
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
