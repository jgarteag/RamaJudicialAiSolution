variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

variable "function_name" {
  description = "Lambda function name suffix"
  type        = string
  default     = "api"
}

variable "handler" {
  description = "Lambda handler (file.function)"
  type        = string
  default     = "handler.lambda_handler"
}

variable "runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "python3.12"
}

variable "memory_size" {
  description = "Lambda memory in MB (128 = cheapest)"
  type        = number
  default     = 128
}

variable "timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 10
}

variable "source_path" {
  description = "Path to the Lambda deployment package (zip)"
  type        = string
}

variable "environment_variables" {
  description = "Environment variables for the Lambda function"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "enable_bedrock" {
  description = "Enable Bedrock invoke permissions for the Lambda"
  type        = bool
  default     = false
}

variable "dynamodb_table_arn" {
  description = "DynamoDB table ARN for read access (empty = no access)"
  type        = string
  default     = ""
}

variable "enable_dynamodb" {
  description = "Enable DynamoDB read permissions"
  type        = bool
  default     = false
}

variable "layer_source_path" {
  description = "Path to the Lambda Layer zip (empty = no layer)"
  type        = string
  default     = ""
}

variable "enable_secrets" {
  description = "Enable Secrets Manager read permissions"
  type        = bool
  default     = false
}

variable "secrets_arns" {
  description = "List of Secrets Manager ARNs to allow read access"
  type        = list(string)
  default     = []
}

variable "bedrock_model_arns" {
  description = "List of Bedrock model/inference-profile ARNs to allow invocation"
  type        = list(string)
  default     = ["arn:aws:bedrock:us-east-1::foundation-model/anthropic.*"]
}
