output "cloud_run_service" { value = google_cloud_run_v2_service.hermes.name }
output "cloud_sql_instance" { value = google_sql_database_instance.hermes.connection_name }
output "artifact_registry" { value = google_artifact_registry_repository.hermes.name }
output "telemetry_dataset" { value = google_bigquery_dataset.telemetry.dataset_id }
