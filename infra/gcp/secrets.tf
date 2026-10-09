resource "google_secret_manager_secret" "model_gateway_api_key" {
  secret_id = "hermes-model-gateway-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "model_gateway_runtime_access" {
  secret_id = google_secret_manager_secret.model_gateway_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.hermes.email}"
}
