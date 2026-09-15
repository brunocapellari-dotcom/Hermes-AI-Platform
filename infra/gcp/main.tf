resource "google_service_account" "hermes" {
  account_id   = "hermes-ai-platform"
  display_name = "Hermes AI Platform runtime"
}

resource "google_artifact_registry_repository" "hermes" {
  location      = var.region
  repository_id = "hermes-ai-platform"
  format        = "DOCKER"
}

resource "google_sql_database_instance" "hermes" {
  name                = "hermes-${var.environment}"
  database_version    = "POSTGRES_17"
  region              = var.region
  deletion_protection = true

  settings {
    tier              = var.db_tier
    availability_type = "REGIONAL"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    ip_configuration {
      ipv4_enabled = false
    }
  }
}

resource "google_sql_database" "hermes" {
  name     = "hermes"
  instance = google_sql_database_instance.hermes.name
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "hermes-database-url"

  replication {
    auto {}
  }
}

resource "google_bigquery_dataset" "telemetry" {
  dataset_id                 = "hermes_telemetry"
  location                   = var.region
  delete_contents_on_destroy = false
}

resource "google_cloud_run_v2_service" "hermes" {
  name                = var.service_name
  location            = var.region
  deletion_protection = true

  template {
    service_account = google_service_account.hermes.email

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      env {
        name  = "HERMES_ENVIRONMENT"
        value = "production"
      }

      env {
        name  = "HERMES_AUTO_CREATE_SCHEMA"
        value = "false"
      }

      env {
        name = "HERMES_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }
    }
  }
}
