output "cloud_run_service" {
  value = var.runtime_enabled ? google_cloud_run_v2_service.hermes[0].name : null
}

output "cloud_run_worker_pool" {
  value = var.runtime_enabled ? google_cloud_run_v2_worker_pool.hermes_worker[0].name : null
}

output "cloud_run_migration_job" {
  value = var.migration_job_enabled ? google_cloud_run_v2_job.hermes_migration[0].name : null
}

output "cloud_sql_instance" {
  value = google_sql_database_instance.hermes.connection_name
}

output "runtime_service_account" {
  value = google_service_account.hermes.email
}

output "migration_service_account" {
  value = google_service_account.hermes_migration.email
}

output "runtime_database_user" {
  value = local.runtime_db_user
}

output "migration_database_user" {
  value = local.migration_db_user
}

output "artifact_registry" {
  value = google_artifact_registry_repository.hermes.name
}

output "telemetry_dataset" {
  value = google_bigquery_dataset.telemetry.dataset_id
}

output "vpc_network" {
  value = google_compute_network.hermes.name
}

output "application_database" {
  value = google_sql_database.hermes.name
}

output "workflow_database" {
  value = var.dbos_reference_enabled ? google_sql_database.hermes_workflows[0].name : null
}
