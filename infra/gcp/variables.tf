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
