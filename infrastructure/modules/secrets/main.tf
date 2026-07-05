# ==============================================================================
# Secrets Manager - Secure storage for connection strings
# Cost: $0.40/secret/month + $0.05 per 10,000 API calls
# With caching in Lambda, API calls will be minimal
# ==============================================================================

resource "aws_secretsmanager_secret" "this" {
  name                    = "${var.project_name}/${var.environment}/${var.secret_name}"
  description             = var.description
  recovery_window_in_days = 0 # No recovery needed in dev (immediate delete)

  tags = var.tags
}
