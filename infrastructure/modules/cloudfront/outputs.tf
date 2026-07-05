output "distribution_id" {
  description = "ID de la distribución CloudFront"
  value       = aws_cloudfront_distribution.frontend.id
}

output "distribution_arn" {
  description = "ARN de la distribución CloudFront"
  value       = aws_cloudfront_distribution.frontend.arn
}

output "distribution_domain_name" {
  description = "Domain name de CloudFront (URL del sitio)"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "oac_id" {
  description = "ID del Origin Access Control"
  value       = aws_cloudfront_origin_access_control.frontend.id
}
