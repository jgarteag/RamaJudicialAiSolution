variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "secret_name" {
  description = "Short name for the secret (e.g. mongodb-uri)"
  type        = string
}

variable "description" {
  description = "Description of the secret"
  type        = string
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
