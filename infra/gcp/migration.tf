resource "google_cloud_run_v2_job" "hermes_migration" {
  count               = var.migration_job_enabled ? 1 : 0
  name                = var.migration_job_name
  location            = var.region
  deletion_protection = true
  launch_stage        = "BETA"

  template {
    template {
      service_account = google_service_account.hermes_migration.email
      max_retries     = 0
      timeout         = "1800s"

      containers {
        image   = var.container_image
        command = ["hermes-migrate-db"]

        env {
          name  = "HERMES_ENVIRONMENT"
          value = "production"
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
          value = local.migration_db_user
        }

        env {
          name  = "HERMES_CLOUD_SQL_IP_TYPE"
          value = "private"
        }

        env {
          name  = "HERMES_RUNTIME_DB_USER"
          value = local.runtime_db_user
        }
      }

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.hermes.name
          subnetwork = google_compute_subnetwork.hermes.name
          tags       = ["hermes-migration"]
        }
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_project_iam_member.migration_cloudsql_client,
    google_project_iam_member.migration_cloudsql_instance_user,
    google_sql_user.hermes_migration,
    google_sql_user.hermes_runtime,
  ]
}
