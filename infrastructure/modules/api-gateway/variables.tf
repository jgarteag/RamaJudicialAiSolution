variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

variable "lambda_invoke_arn" {
  description = "Lambda function invoke ARN for integration"
  type        = string
}

variable "lambda_function_name" {
  description = "Lambda function name for permission"
  type        = string
}

variable "allowed_origins" {
  description = "Allowed origins for CORS"
  type        = list(string)
  default     = ["*"]
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "cognito_user_pool_endpoint" {
  description = "Cognito User Pool endpoint (empty = no auth)"
  type        = string
  default     = ""
}

variable "cognito_client_id" {
  description = "Cognito App Client ID"
  type        = string
  default     = ""
}

variable "enable_auth" {
  description = "Enable JWT auth on protected routes"
  type        = bool
  default     = false
}
