# ==============================================================================
# Lambda Function - Serverless Compute (pay per invocation)
# 128MB = cheapest tier (~$0.0000002 per 100ms)
# Free tier: 1M requests + 400,000 GB-seconds/month
# ==============================================================================

locals {
  function_name = "${var.project_name}-${var.function_name}-${var.environment}"
}

# Lambda Layer (optional - for external dependencies)
resource "aws_lambda_layer_version" "deps" {
  count               = var.layer_source_path != "" ? 1 : 0
  layer_name          = "${local.function_name}-deps"
  filename            = var.layer_source_path
  source_code_hash    = filebase64sha256(var.layer_source_path)
  compatible_runtimes = [var.runtime]
}

resource "aws_lambda_function" "main" {
  function_name = local.function_name
  role          = aws_iam_role.lambda.arn
  handler       = var.handler
  runtime       = var.runtime
  memory_size   = var.memory_size
  timeout       = var.timeout

  filename         = var.source_path
  source_code_hash = filebase64sha256(var.source_path)

  layers = var.layer_source_path != "" ? [aws_lambda_layer_version.deps[0].arn] : []

  environment {
    variables = merge(
      {
        ENVIRONMENT = var.environment
        PROJECT     = var.project_name
      },
      var.environment_variables
    )
  }

  tags = var.tags
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda" {
  name = "${local.function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# Basic execution policy (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Bedrock invoke policy (optional)
resource "aws_iam_role_policy" "bedrock" {
  count = var.enable_bedrock ? 1 : 0
  name  = "${local.function_name}-bedrock"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/anthropic.*",
          "arn:aws:bedrock:*:*:inference-profile/us.anthropic.*"
        ]
      }
    ]
  })
}

# CloudWatch Log Group (explicit to control retention)
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = 14

  tags = var.tags
}

# DynamoDB read policy (optional)
resource "aws_iam_role_policy" "dynamodb" {
  count = var.enable_dynamodb ? 1 : 0
  name  = "${local.function_name}-dynamodb"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = var.dynamodb_table_arn
      }
    ]
  })
}

# Secrets Manager read policy (optional)
resource "aws_iam_role_policy" "secrets" {
  count = var.enable_secrets ? 1 : 0
  name  = "${local.function_name}-secrets"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = var.secrets_arns
      }
    ]
  })
}
