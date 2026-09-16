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

variable "worker_pool_name" {
  description = "Cloud Run worker pool that executes durable DBOS mission workflows."
  type        = string
  default     = "hermes-ai-worker"
}

variable "worker_instance_count" {
  description = "Manual DBOS worker count. Keep one until live load and queue telemetry justify scaling."
  type        = number
  default     = 1

  validation {
    condition     = var.worker_instance_count >= 1 && var.worker_instance_count <= 20
    error_message = "worker_instance_count must be between 1 and 20."
  }
}

variable "migration_job_name" {
  description = "Cloud Run Job used only for controlled Alembic + DBOS migrations."
  type        = string
  default     = "hermes-db-migrate"
}

variable "migration_job_enabled" {
  description = "Create the migration job without executing it. Enable after a reviewed image exists."
  type        = bool
  default     = false
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
  description = "Enable Cloud Run API and worker only after IAM database users, migrations and live gates are ready."
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/24"
}
