output "secret_arn" {
  description = "ARN of the secret"
  value       = aws_secretsmanager_secret.this.arn
}

output "secret_name" {
  description = "Full name of the secret"
  value       = aws_secretsmanager_secret.this.name
}
