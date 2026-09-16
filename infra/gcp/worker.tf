resource "google_cloud_run_v2_worker_pool" "hermes_worker" {
  count               = var.runtime_enabled ? 1 : 0
  name                = var.worker_pool_name
  location            = var.region
  launch_stage        = "BETA"
  deletion_protection = true

  scaling {
    scaling_mode         = "MANUAL"
    manual_instance_count = var.worker_instance_count
  }

  template {
    service_account = google_service_account.hermes.email

    containers {
      image   = var.container_image
      command = ["hermes-worker"]

      env {
        name  = "HERMES_ENVIRONMENT"
        value = "production"
      }

      env {
        name  = "HERMES_AUTO_CREATE_SCHEMA"
        value = "false"
      }

      env {
        name  = "HERMES_SERVICE_TO_SERVICE_AUTH"
        value = "true"
      }

      env {
        name  = "HERMES_ALLOW_EXTERNAL_ACTIONS"
        value = "false"
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
        name  = "HERMES_DBOS_APPLICATION_NAME"
        value = "hermes-worker"
      }

      env {
        name  = "HERMES_DBOS_QUEUE_NAME"
        value = "hermes-missions"
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
        tags       = ["hermes-worker"]
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
