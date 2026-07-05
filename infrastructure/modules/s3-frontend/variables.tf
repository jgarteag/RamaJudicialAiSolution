variable "project_name" {
  description = "Nombre del proyecto"
  type        = string
}

variable "environment" {
  description = "Ambiente (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "suffix" {
  description = "Sufijo único para evitar colisiones de nombres"
  type        = string
}

variable "cloudfront_distribution_arn" {
  description = "ARN de la distribución CloudFront (para bucket policy)"
  type        = string
}

variable "tags" {
  description = "Tags comunes para los recursos"
  type        = map(string)
  default     = {}
}
