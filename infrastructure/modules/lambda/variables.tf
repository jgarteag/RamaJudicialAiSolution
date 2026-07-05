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
