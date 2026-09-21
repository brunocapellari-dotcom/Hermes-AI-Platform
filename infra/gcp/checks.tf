check "immutable_release_identity" {
  assert {
    condition = !(
      var.runtime_enabled ||
      var.migration_job_enabled ||
      var.dbos_reference_enabled
    ) || length(trimspace(var.release_version)) >= 7

    error_message = "release_version must identify the exact immutable release/commit before runtime, migration, or DBOS benchmark resources are enabled."
  }
}

check "external_authorization_endpoints" {
  assert {
    condition = !var.runtime_enabled || !var.external_authorization_required || (
      var.opa_url != "" &&
      var.openfga_url != "" &&
      var.openfga_store_id != ""
    )

    error_message = "external_authorization_required=true requires OPA URL plus OpenFGA URL/store configuration before runtime planning."
  }
}
