output "bucket_id" {
  description = "ID del bucket S3"
  value       = aws_s3_bucket.frontend.id
}

output "bucket_arn" {
  description = "ARN del bucket S3"
  value       = aws_s3_bucket.frontend.arn
}

output "bucket_regional_domain_name" {
  description = "Domain name regional del bucket (para CloudFront origin)"
  value       = aws_s3_bucket.frontend.bucket_regional_domain_name
}
