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
