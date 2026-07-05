# ==============================================================================
# API Gateway HTTP API (v2) - Low Cost
# ~$1.00 per million requests vs $3.50 for REST API
# No minimum fees, no stage costs, pure pay-per-request
# ==============================================================================

resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project_name}-api-${var.environment}"
  protocol_type = "HTTP"
  description   = "HTTP API for ${var.project_name} (${var.environment})"

  cors_configuration {
    allow_origins = var.allowed_origins
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 86400
  }

  tags = var.tags
}

# Auto-deploy stage (no extra cost for HTTP API stages)
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      method         = "$context.httpMethod"
      path           = "$context.path"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      latency        = "$context.integrationLatency"
    })
  }

  tags = var.tags
}

# CloudWatch log group for access logs
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}"
  retention_in_days = 14

  tags = var.tags
}

# Lambda integration
resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.lambda_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# JWT Authorizer (Cognito)
resource "aws_apigatewayv2_authorizer" "cognito" {
  count = var.enable_auth ? 1 : 0

  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-jwt"

  jwt_configuration {
    audience = [var.cognito_client_id]
    issuer   = "https://${var.cognito_user_pool_endpoint}"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Routes - Health (public, no auth)
resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /api/health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# Routes - Protected (require JWT if auth enabled)
resource "aws_apigatewayv2_route" "chat" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /api/chat"
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorization_type = var.enable_auth ? "JWT" : "NONE"
  authorizer_id      = var.enable_auth ? aws_apigatewayv2_authorizer.cognito[0].id : null
}

resource "aws_apigatewayv2_route" "upload" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /api/upload"
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorization_type = var.enable_auth ? "JWT" : "NONE"
  authorizer_id      = var.enable_auth ? aws_apigatewayv2_authorizer.cognito[0].id : null
}

resource "aws_apigatewayv2_route" "juzgados" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /api/juzgados"
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorization_type = var.enable_auth ? "JWT" : "NONE"
  authorizer_id      = var.enable_auth ? aws_apigatewayv2_authorizer.cognito[0].id : null
}

# Permission for API Gateway to invoke Lambda
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}
