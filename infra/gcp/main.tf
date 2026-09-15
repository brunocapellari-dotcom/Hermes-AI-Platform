locals {
  required_services = toset([
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "compute.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
  ])
}

resource "google_project_service" "required" {
  for_each           = local.required_services
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "hermes" {
  account_id   = "hermes-ai-platform"
  display_name = "Hermes AI Platform runtime"
}

resource "google_artifact_registry_repository" "hermes" {
  location      = var.region
  repository_id = "hermes-ai-platform"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}

resource "google_compute_network" "hermes" {
  name                    = "hermes-${var.environment}"
  auto_create_subnetworks = false

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "hermes" {
  name                     = "hermes-${var.environment}-${var.region}"
  region                   = var.region
  network                  = google_compute_network.hermes.id
  ip_cidr_range            = var.vpc_cidr
  private_ip_google_access = true
}

resource "google_compute_global_address" "private_services" {
  name          = "hermes-${var.environment}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.hermes.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.hermes.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]

  depends_on = [google_project_service.required]
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
      ipv4_enabled    = false
      private_network = google_compute_network.hermes.id
    }
  }

  depends_on = [google_service_networking_connection.private_vpc]
}

resource "google_sql_database" "hermes" {
  name     = "hermes"
  instance = google_sql_database_instance.hermes.name
}

resource "google_sql_database" "hermes_workflows" {
  name     = "hermes_workflows"
  instance = google_sql_database_instance.hermes.name
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "hermes-database-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "dbos_database_url" {
  secret_id = "hermes-dbos-system-database-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "database_url_runtime" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.hermes.email}"
}

resource "google_secret_manager_secret_iam_member" "dbos_url_runtime" {
  secret_id = google_secret_manager_secret.dbos_database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.hermes.email}"
}

resource "google_bigquery_dataset" "telemetry" {
  dataset_id                 = "hermes_telemetry"
  location                   = var.region
  delete_contents_on_destroy = false

  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service" "hermes" {
  count               = var.runtime_enabled ? 1 : 0
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
            version = var.database_secret_version
          }
        }
      }

      env {
        name = "HERMES_DBOS_SYSTEM_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.dbos_database_url.secret_id
            version = var.dbos_secret_version
          }
        }
      }
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.hermes.name
        subnetwork = google_compute_subnetwork.hermes.name
        tags       = ["hermes-api"]
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_iam_member.database_url_runtime,
    google_secret_manager_secret_iam_member.dbos_url_runtime,
  ]
}
