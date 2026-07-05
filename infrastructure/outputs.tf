# ============================================
# Outputs - Información útil post-deploy
# ============================================

output "website_url" {
  description = "URL del sitio web (CloudFront)"
  value       = "https://${module.cloudfront.distribution_domain_name}"
}

output "cloudfront_distribution_id" {
  description = "ID de la distribución CloudFront (para invalidar cache)"
  value       = module.cloudfront.distribution_id
}

output "s3_bucket_id" {
  description = "ID del bucket S3 del frontend"
  value       = module.s3_frontend.bucket_id
}

output "cloudfront_domain" {
  description = "Domain name de CloudFront"
  value       = module.cloudfront.distribution_domain_name
}

# ============================================
# Microstack 2 - Backend API Outputs
# ============================================

output "api_endpoint" {
  description = "URL del API Gateway HTTP API"
  value       = module.api_gateway.api_endpoint
}

output "lambda_function_name" {
  description = "Nombre de la función Lambda"
  value       = module.lambda_api.function_name
}

output "cognito_user_pool_id" {
  value = module.cognito.user_pool_id
}

output "cognito_client_id" {
  value = module.cognito.client_id
}
