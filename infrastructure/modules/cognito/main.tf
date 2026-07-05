# ==============================================================================
# Cognito User Pool - Authentication
# Cost: FREE for first 50,000 MAU (monthly active users)
# No custom domain = $0 extra
# ==============================================================================

resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-${var.environment}"

  # Email as username
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Password policy (reasonable defaults)
  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  # Account recovery via email
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Schema: just email, keep it simple
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 5
      max_length = 100
    }
  }

  # Self sign-up enabled
  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  # Email verification message
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Tu código de verificación - Estados Judiciales IA"
    email_message        = "Tu código de verificación es: {####}"
  }

  tags = var.tags
}

# App Client (public - for SPA, no secret)
resource "aws_cognito_user_pool_client" "spa" {
  name         = "${var.project_name}-spa-${var.environment}"
  user_pool_id = aws_cognito_user_pool.main.id

  # No secret for SPA (public client)
  generate_secret = false

  # Auth flows for SPA
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH",
  ]

  # Token validity
  access_token_validity  = 1  # 1 hour
  id_token_validity      = 1  # 1 hour
  refresh_token_validity = 30 # 30 days

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # Prevent user existence errors (security)
  prevent_user_existence_errors = "ENABLED"

  supported_identity_providers = ["COGNITO"]
}
