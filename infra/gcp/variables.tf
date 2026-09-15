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

variable "container_image" {
  type = string
}

variable "db_tier" {
  type    = string
  default = "db-custom-1-3840"
}

variable "runtime_enabled" {
  description = "Enable Cloud Run only after secret versions exist."
  type        = bool
  default     = false
}

variable "database_secret_version" {
  description = "Pinned Secret Manager version containing the Hermes application DB URL."
  type        = string
  default     = "1"
}

variable "dbos_secret_version" {
  description = "Pinned Secret Manager version containing the DBOS system DB URL."
  type        = string
  default     = "1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/24"
}
