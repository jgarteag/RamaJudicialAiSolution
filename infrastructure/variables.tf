# ============================================
# Variables de entrada - Root Module
# ============================================

variable "project_name" {
  description = "Nombre del proyecto (usado en nombres de recursos)"
  type        = string
  default     = "rama-judicial-ai"
}

variable "environment" {
  description = "Ambiente de despliegue"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "El ambiente debe ser: dev, staging o prod."
  }
}

variable "aws_region" {
  description = "Región AWS"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Perfil AWS CLI (null en CI/CD)"
  type        = string
  default     = null
}

variable "cloudfront_price_class" {
  description = "Price class de CloudFront"
  type        = string
  default     = "PriceClass_100"
}
