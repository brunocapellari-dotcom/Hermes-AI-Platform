# Google Cloud Production Runbook

This runbook is preparation only. No Google Cloud resource should be created from another environment until the integrated GitHub release candidate is green and the repository security blocker is resolved.

## Canonical target

- Cloud Run: Hermes API and, when validated for the queue workload, a durable worker deployment.
- Cloud SQL PostgreSQL 17: operational Hermes state and a separate logical DB for DBOS workflows.
- Secret Manager: all credentials and connection strings; secrets are not stored in Git, `.env.example`, Terraform variables or Terraform state.
- Private VPC / private Cloud SQL access / Direct VPC egress.
- Artifact Registry: immutable container artifacts.
- BigQuery: analytical telemetry only; not the operational source of truth.
- OpenTelemetry: standard trace/metric export.

## Activation gate

1. Repository CI must be fully green: lint, strict typing, security scan, dependency audit, database migration, pytest coverage >=90%, container build and Terraform validation.
2. Repository must be private before internal endpoints, production metadata or credentials are introduced.
3. Select/confirm GCP project, billing and region explicitly.
4. Run Terraform for the base infrastructure with `runtime_enabled=false`.
5. Populate pinned Secret Manager versions through an authorized secret path outside Terraform.
6. Run `alembic upgrade head` against the target Cloud SQL database from a controlled migration job/identity.
7. Build/push the exact green commit to Artifact Registry.
8. Enable runtime only after database migration and secret/version checks succeed.
9. Run live smoke tests, OPA/OpenFGA authorization tests, model/provider fallback, project contracts and DBOS recovery/idempotency tests.
10. Exercise backup restore and rollback before production status is allowed.

## Rollback

- Runtime rollback selects the previous immutable container revision.
- Schema changes require a reviewed Alembic downgrade/forward-fix strategy; destructive rollback is never automatic.
- Cloud SQL PITR/backup is the disaster-recovery boundary, not a substitute for migration discipline.
- A failed live gate returns the release to non-operational status; documentation cannot override failing evidence.
