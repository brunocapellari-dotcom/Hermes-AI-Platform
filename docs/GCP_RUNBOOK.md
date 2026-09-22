# Google Cloud Production Runbook

This runbook is preparation only. No Google Cloud resource should be created from another environment until the integrated GitHub release candidate is green and the repository security gate is resolved.

## Canonical target

- Cloud Run: Hermes API.
- Durable worker/runtime: engine-neutral architecture. The current Terraform/worker implementation is DBOS reference infrastructure only until the DBOS/Temporal/Restate benchmark selects one canonical engine.
- Cloud SQL PostgreSQL 17: Hermes operational state. A DBOS workflow database is created only while DBOS remains the reference candidate and must not be treated as permanent architecture before benchmark selection.
- Cloud SQL Python Connector + automatic IAM database authentication: canonical production connection path; no static database password or database-URL secret.
- Separate runtime and migration service accounts. Runtime receives only Cloud SQL client/login IAM roles; the migration identity is the controlled privileged database identity.
- Secret Manager: provider/API credentials and other secrets that cannot use workload identity.
- Private VPC / private Cloud SQL access / Direct VPC egress.
- Artifact Registry: immutable container artifacts.
- BigQuery: analytical telemetry only; never operational source of truth.
- OpenTelemetry: canonical trace/metric transport.
- Langfuse: preferred optional AI-observability backend over OpenTelemetry. It must be removable without changing Hermes correctness; Phoenix is reserve only.

## Durable-engine gate before production runtime

Do not permanently enable a durable worker merely because the DBOS adapter exists.

Before final production architecture:
1. Execute the canonical benchmark in docs/DURABLE_ENGINE_BENCHMARK.md for DBOS, Temporal and Restate.
2. Require every selected candidate to pass all mandatory scenarios.
3. Require zero duplicate external side effects.
4. Compare recovery correctness, version upgrades, operator recovery, infrastructure burden, observability, performance and cost.
5. Select exactly one canonical production durable engine.
6. Update Terraform to retain only the selected engine's production resources.
7. Remove candidate-specific runtime dependencies/resources that are no longer required.

Until this benchmark is complete, DBOS Terraform resources are a reference candidate and runtime_enabled must not be interpreted as final production approval.

## Connection contract for the DBOS reference candidate

While DBOS is under benchmark, the reference deployment uses HERMES_DATABASE_URL=cloudsql+iam:///hermes and HERMES_DBOS_SYSTEM_DATABASE_URL=cloudsql+iam:///hermes_workflows.

Non-secret connector settings are HERMES_CLOUD_SQL_INSTANCE_CONNECTION_NAME, the trimmed lowercase PostgreSQL IAM username in HERMES_CLOUD_SQL_IAM_USER, and HERMES_CLOUD_SQL_IP_TYPE=private.

The runtime IAM database user is intentionally created with no database-object privileges. After schema migration, the controlled migration identity grants only the privileges Hermes/DBOS needs. Runtime DBOS processes use run_migrations=false and fail if required schema is absent or incompatible.

If Temporal or Restate wins the durable benchmark, remove DBOS-specific database/runtime resources that no longer serve another canonical responsibility.

## Service-to-service security

- Cloud Run API remains private.
- roles/run.invoker is granted only to the explicit service_invoker_members allowlist.
- allUsers and allAuthenticatedUsers are rejected by Terraform validation.
- Hermes validates its own application identity/authorization boundaries in addition to Cloud Run ingress IAM.
- Private model gateways may use X-Serverless-Authorization for Cloud Run IAM while preserving Authorization for model-gateway API keys.
- OPA/OpenFGA Cloud Run IAM authentication is opt-in through explicit audiences; do not send Google identity tokens to unrelated external services.
- Production external_authorization_required defaults true and fails closed when required policy services are unavailable.

## Observability

HERMES_OTLP_ENDPOINT is the vendor-neutral export target.

Preferred production sequence:
1. prove Hermes API and durable-engine spans through OTLP;
2. prove mission/workflow/model/tool/project correlation;
3. point OTLP to Langfuse when an AI-specific trace/evaluation UI is useful;
4. keep PostgreSQL audit/usage ledgers authoritative for operational evidence and FinOps;
5. export analytical telemetry to BigQuery separately.

Langfuse deployment, storage and authentication are optional infrastructure choices. Do not couple business logic to Langfuse APIs unless an explicit feature requires it. Phoenix is a reserve alternative, not a parallel default.

## Evaluation gate

Promptfoo is a release-test dependency, not a Hermes runtime dependency. Run endpoint regression/red-team only against an authorized non-production or controlled staging target first.

Ragas is introduced only when a live RAG/Second Brain path exists and must not become a general agent test framework.

DeepEval remains optional and may be installed only when a concrete Python-specific evaluation gap exists.

## Activation gate

1. Repository CI must be fully green on the exact release commit: lint, strict typing, security scan, dependency audit, database migration, pytest coverage >=90%, container build, OPA/OpenFGA validation, supply-chain scans and Terraform validation.
2. Repository must remain private before internal endpoints, production metadata or credentials are introduced.
3. Durable-engine benchmark must have an explicit selected engine before declaring final production architecture.
4. Model-gateway benchmark must preserve LiteLLM as the selected gateway unless Bifrost demonstrates a measured replacement advantage.
5. A generated and verified uv.lock is required before the immutable production artifact is built.
6. Select/confirm GCP project, billing and region explicitly.
7. Run Terraform for base infrastructure with runtime_enabled=false.
8. Verify Cloud SQL IAM/private networking only for database resources still required by the selected architecture.
9. Execute controlled application migrations under the migration identity.
10. If DBOS is selected, initialize/migrate its system schema under the migration identity and verify runtime DML-only permissions.
11. Build/push the exact green commit to Artifact Registry.
12. Configure private service identities, OPA/OpenFGA and explicit Cloud Run invokers.
13. Configure model gateway/local model adapters and OpenTelemetry exporter.
14. Enable runtime only after database/schema/IAM/readiness/policy checks succeed.
15. Run project adapter contracts, model fallback, privacy/MCP adversarial tests, sandbox tests and the selected durable engine's crash/idempotency suite.
16. Run Promptfoo live regression/red-team.
17. Run Ragas only if RAG is enabled.
18. Verify OpenTelemetry trace correlation; add Langfuse if selected as the observability UI/backend.
19. Exercise backup restore and rollback before production status is allowed.

## Rollback

- Runtime rollback selects the previous immutable container revision.
- Durable engine upgrade/rollback follows that engine's explicit versioning and state-compatibility procedure; never assume workflow histories/state are backward-compatible.
- Schema changes require a reviewed Alembic downgrade/forward-fix strategy; destructive rollback is never automatic.
- Cloud SQL PITR/backup is the disaster-recovery boundary for data stored there, not a substitute for migration discipline.
- A failed live gate returns the release to non-operational status; documentation cannot override failing evidence.
