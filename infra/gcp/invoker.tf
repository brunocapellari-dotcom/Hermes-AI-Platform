resource "google_cloud_run_v2_service_iam_member" "hermes_invoker" {
  for_each = var.runtime_enabled ? var.service_invoker_members : toset([])

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.hermes[0].name
  role     = "roles/run.invoker"
  member   = each.value
}
