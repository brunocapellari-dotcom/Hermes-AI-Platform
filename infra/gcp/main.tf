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
  runtime_db_user   = trimsuffix(google_service_account.hermes.email, ".gserviceaccount.com")
  migration_db_user = trimsuffix(google_service_account.hermes_migration.email, ".gserviceaccount.com")
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

resource "google_service_account" "hermes_migration" {
  account_id   = "hermes-db-migration"
  display_name = "Hermes database migration identity"
}

resource "google_project_iam_member" "hermes_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.hermes.email}"
}

resource "google_project_iam_member" "hermes_cloudsql_instance_user" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.hermes.email}"
}

resource "google_project_iam_member" "migration_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.hermes_migration.email}"
}

resource "google_project_iam_member" "migration_cloudsql_instance_user" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.hermes_migration.email}"
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

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

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

resource "google_sql_user" "hermes_runtime" {
  name     = local.runtime_db_user
  instance = google_sql_database_instance.hermes.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

resource "google_sql_user" "hermes_migration" {
  name           = local.migration_db_user
  instance       = google_sql_database_instance.hermes.name
  type           = "CLOUD_IAM_SERVICE_ACCOUNT"
  database_roles = ["cloudsqlsuperuser"]
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
  custom_audiences    = [var.service_auth_audience]

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
        name  = "HERMES_SERVICE_AUTH_REQUIRED"
        value = "true"
      }

      env {
        name  = "HERMES_SERVICE_AUTH_AUDIENCE"
        value = var.service_auth_audience
      }

      env {
        name  = "HERMES_DATABASE_URL"
        value = "cloudsql+iam:///hermes"
      }

      env {
        name  = "HERMES_DBOS_SYSTEM_DATABASE_URL"
        value = "cloudsql+iam:///hermes_workflows"
      }

      env {
        name  = "HERMES_CLOUD_SQL_INSTANCE_CONNECTION_NAME"
        value = google_sql_database_instance.hermes.connection_name
      }

      env {
        name  = "HERMES_CLOUD_SQL_IAM_USER"
        value = local.runtime_db_user
      }

      env {
        name  = "HERMES_CLOUD_SQL_IP_TYPE"
        value = "private"
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
    google_project_iam_member.hermes_cloudsql_client,
    google_project_iam_member.hermes_cloudsql_instance_user,
    google_sql_user.hermes_runtime,
  ]
}
