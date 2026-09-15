variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "southamerica-east1"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "service_name" {
  type    = string
  default = "hermes-ai-platform"
}

variable "service_auth_audience" {
  description = "Stable custom OIDC audience for service-to-service Hermes calls."
  type        = string
  default     = "https://hermes.internal"
}

variable "container_image" {
  type = string
}

variable "db_tier" {
  type    = string
  default = "db-custom-1-3840"
}

variable "runtime_enabled" {
  description = "Enable Cloud Run only after IAM database users, migrations and live gates are ready."
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/24"
}
