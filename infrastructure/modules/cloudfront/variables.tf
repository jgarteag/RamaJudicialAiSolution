variable "project_name" {
  description = "Nombre del proyecto"
  type        = string
}

variable "environment" {
  description = "Ambiente (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "s3_bucket_regional_domain_name" {
  description = "Domain name regional del bucket S3 (origin)"
  type        = string
}

variable "price_class" {
  description = "Price class de CloudFront (PriceClass_100 = US/Europe, PriceClass_200 = + Asia, PriceClass_All = Global)"
  type        = string
  default     = "PriceClass_100"
}

variable "tags" {
  description = "Tags comunes para los recursos"
  type        = map(string)
  default     = {}
}
