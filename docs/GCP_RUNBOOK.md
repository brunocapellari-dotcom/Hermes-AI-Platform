# Google Cloud Production Runbook

This runbook is preparation only. No Google Cloud resource should be created from another environment until the integrated GitHub release candidate is green and the repository security blocker is resolved.

## Canonical target

- Cloud Run: Hermes API and, when validated for the queue workload, a durable worker deployment.
- Cloud SQL PostgreSQL 17: operational Hermes state and a separate logical DB for DBOS workflows.
- Cloud SQL Python Connector + automatic IAM database authentication: canonical production connection path; no static database password or database-URL secret.
- Separate runtime and migration service accounts. Runtime receives only Cloud SQL client/login IAM roles; the migration identity is the controlled privileged database identity.
- Secret Manager: provider/API credentials and other secrets that cannot use workload identity; database passwords are not part of the canonical design.
- Private VPC / private Cloud SQL access / Direct VPC egress.
- Artifact Registry: immutable container artifacts.
- BigQuery: analytical telemetry only; not the operational source of truth.
- OpenTelemetry: standard trace/metric export.

## Connection contract

Production uses `HERMES_DATABASE_URL=cloudsql+iam:///hermes` and `HERMES_DBOS_SYSTEM_DATABASE_URL=cloudsql+iam:///hermes_workflows`. The non-secret connector settings are `HERMES_CLOUD_SQL_INSTANCE_CONNECTION_NAME`, the trimmed lowercase PostgreSQL IAM username in `HERMES_CLOUD_SQL_IAM_USER`, and `HERMES_CLOUD_SQL_IP_TYPE=private`.

The runtime IAM database user is intentionally created with no database-object privileges. After schema migration, the controlled migration identity must grant only the privileges Hermes needs on the `hermes` and `hermes_workflows` databases. This grant/bootstrap is a live activation step and must be evidenced before runtime is enabled.

## Activation gate

1. Repository CI must be fully green: lint, strict typing, security scan, dependency audit, database migration, pytest coverage >=90%, container build, authorization-policy validation and Terraform validation.
2. Repository must be private before internal endpoints, production metadata or credentials are introduced.
3. Select/confirm GCP project, billing and region explicitly.
4. Run Terraform for the base infrastructure with `runtime_enabled=false`; verify Cloud SQL IAM authentication, private networking, the runtime IAM user, migration IAM user and least-privilege project bindings.
5. Execute `alembic upgrade head` against `cloudsql+iam:///hermes` under the migration identity using the Cloud SQL Python Connector.
6. Initialize/migrate the DBOS system schema in `hermes_workflows` under the migration identity, then grant the runtime database user only required DML/sequence/schema permissions in both databases.
7. Build/push the exact green commit to Artifact Registry.
8. Enable runtime only after migration, grants, IAM login, readiness and policy checks succeed.
9. Run live smoke tests, OPA/OpenFGA authorization tests, model/provider fallback, project contracts, privacy/MCP adversarial tests and DBOS recovery/idempotency tests.
10. Exercise backup restore and rollback before production status is allowed.

## Rollback

- Runtime rollback selects the previous immutable container revision.
- Schema changes require a reviewed Alembic downgrade/forward-fix strategy; destructive rollback is never automatic.
- Cloud SQL PITR/backup is the disaster-recovery boundary, not a substitute for migration discipline.
- A failed live gate returns the release to non-operational status; documentation cannot override failing evidence.
