# Zero-Cost Runtime Policy

Hermes must support a go-live path with **zero incremental external service spend**.

This means the production baseline must not require paid cloud infrastructure, paid LLM/API usage, paid databases, paid observability, or paid queues.

It does not mean electricity, internet access, or already-owned hardware have no real-world cost. The operational target is **R$ 0 of additional recurring vendor spend**.

## Canonical zero-cost stack

- Runtime: existing local Linux/Windows/macOS machine.
- API: Hermes FastAPI process bound to localhost by default.
- Database: SQLite for the first operational release.
- Durable state: local database and existing workflow/checkpoint mechanisms.
- Models: local model routes only while `HERMES_ZERO_COST_MODE=true`.
- Model gateway: optional local OpenAI-compatible gateway; no paid remote provider is required.
- Knowledge and project services: local processes or existing connected services that do not incur additional vendor spend.
- Observability: structured local logs, health/readiness endpoints, local metrics.
- Backups: local encrypted copies to another disk/location already available to the owner.
- CI: local full test gate is authoritative when hosted CI quota would create spend.
- Deploy: reproducible local/container deployment first. GCP remains optional post-go-live infrastructure, not a release dependency.

## Required configuration

```env
HERMES_ENVIRONMENT=production
HERMES_ZERO_COST_MODE=true
HERMES_DATABASE_URL=sqlite:///./data/hermes.db
HERMES_MODEL_GATEWAY_URL=
HERMES_MODEL_GATEWAY_API_KEY=
HERMES_SERVICE_AUTH_REQUIRED=false
HERMES_SERVICE_TO_SERVICE_AUTH=false
HERMES_EXTERNAL_AUTHORIZATION_REQUIRED=false
HERMES_ALLOW_EXTERNAL_ACTIONS=false
HERMES_OTLP_ENDPOINT=
```

When a local model gateway is available, set `HERMES_MODEL_GATEWAY_URL` to the local endpoint and register only profiles with `local=true`.

## Fail-closed cost rule

When `HERMES_ZERO_COST_MODE=true`:

1. non-local model profiles are denied by the budget guard;
2. no paid provider key is required for go-live;
3. cloud deployment is optional;
4. adding a paid dependency is a scope change and must not happen automatically;
5. the application remains usable without AI generation if no local model gateway is configured.

## Security constraints

Zero cost does not relax security. Keep the service on localhost unless a reviewed network boundary exists. Do not expose SQLite files, secrets, logs, or internal service ports directly to the internet. External actions remain disabled by default.

## Local go-live sequence

1. Create a local data directory with owner-only permissions.
2. Configure `.env` from `.env.example`.
3. Keep `HERMES_ZERO_COST_MODE=true`.
4. Run migrations or schema creation against local SQLite.
5. Run lint, typecheck, unit, integration, security, and E2E tests locally.
6. Start Hermes locally/containerized.
7. Validate `/health` and `/ready`.
8. Run the selected E2E flows twice with different inputs.
9. Create and restore a local backup.
10. Record the tested commit in `GO_LIVE_STATUS.md`.

## Optional later upgrade

Cloud Run, Cloud SQL, BigQuery, hosted model providers, hosted telemetry, or other paid services can be added later only when the owner explicitly accepts the cost. They are not part of the zero-cost release gate.
