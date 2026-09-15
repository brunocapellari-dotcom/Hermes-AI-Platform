output "cloud_run_service" {
  value = var.runtime_enabled ? google_cloud_run_v2_service.hermes[0].name : null
}

output "cloud_sql_instance" {
  value = google_sql_database_instance.hermes.connection_name
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
  value = google_sql_database.hermes_workflows.name
}
