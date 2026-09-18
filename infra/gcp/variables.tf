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

variable "service_invoker_members" {
  description = "Explicit IAM members allowed to invoke the private Hermes Cloud Run API. Empty keeps the service ungranted by this stack."
  type        = set(string)
  default     = []
}

variable "model_gateway_url" {
  description = "OpenAI-compatible model gateway URL, typically LiteLLM. Empty keeps generation disabled."
  type        = string
  default     = ""
}

variable "model_gateway_api_key_secret_version" {
  description = "Pinned Secret Manager version for the model gateway key. Null means no gateway key is injected."
  type        = string
  default     = null
  nullable    = true
}

variable "default_model" {
  type    = string
  default = ""
}

variable "embedding_model" {
  type    = string
  default = ""
}

variable "vision_model" {
  type    = string
  default = ""
}

variable "transcription_model" {
  type    = string
  default = ""
}

variable "speech_model" {
  type    = string
  default = ""
}

variable "rerank_model" {
  type    = string
  default = ""
}

variable "second_brain_url" {
  type    = string
  default = ""
}

variable "research_url" {
  type    = string
  default = ""
}

variable "opa_url" {
  type    = string
  default = ""
}

variable "openfga_url" {
  type    = string
  default = ""
}

variable "openfga_store_id" {
  type    = string
  default = ""
}

variable "openfga_model_id" {
  type    = string
  default = ""
}

variable "external_authorization_required" {
  description = "Fail closed unless external OPA/OpenFGA authorization is configured for protected operations."
  type        = bool
  default     = true
}

variable "allow_external_actions" {
  description = "Global kill switch for project mutations; keep false until approval/idempotency live tests pass."
  type        = bool
  default     = false
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
