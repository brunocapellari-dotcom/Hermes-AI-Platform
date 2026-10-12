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


## Hardened local container profile

The repository includes `docker-compose.zero-cost.yml`. It binds Hermes only to `127.0.0.1:8080`, drops Linux capabilities, enables `no-new-privileges`, keeps the container filesystem read-only, and persists only the SQLite data volume.

Start:

```bash
docker compose -f docker-compose.zero-cost.yml up -d --build
```

Validate:

```bash
docker compose -f docker-compose.zero-cost.yml ps
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/ready
```

Stop without deleting data:

```bash
docker compose -f docker-compose.zero-cost.yml down
```

Do not add `-v` to the down command unless the SQLite volume is intentionally being destroyed.

## Backup and restore drill

The local runtime includes a verified SQLite backup/restore CLI. It refuses to overwrite an existing destination and runs SQLite integrity checks before and after copying.

```bash
hermes-local-db backup ./data/hermes.db ./backups/hermes-backup.db
hermes-local-db restore ./backups/hermes-backup.db ./restore-test/hermes.db
```

After a successful restore drill, validate the restored database before replacing any production file. Backup confidentiality depends on host storage protection; use the operating system's disk/device encryption for the data and backup locations when available.


## Operational worker

The API admits and persists work; the operational worker performs project execution and drains the durable event outbox. In the zero-cost release it runs as a second local process against the same SQLite file.

Start the API:

```bash
uvicorn hermes.asgi:app --host 127.0.0.1 --port 8080
```

Start the worker in another local process:

```bash
hermes-operational-worker
```

For an integration smoke cycle without a long-running loop:

```bash
hermes-operational-worker --once
```

When the local Holding is running on port 8001, keep:

```env
HERMES_HOLDING_URL=http://127.0.0.1:8001
```

The worker uses the same durable SQLite state, P0-P3 ordering, leases, heartbeats, bounded retries, checkpoints and outbox/DLQ. The SQLite runtime enables foreign keys, a 30-second busy timeout and WAL mode for file-backed databases so the API and worker can share the local database safely.

Do not expose the local worker or SQLite file to the network. Project and Holding endpoints must remain HTTPS or loopback HTTP under the zero-cost policy.


## Worker readiness gate

For the final local go-live smoke, enable the worker dependency gate after both API and worker are configured to use the same SQLite file:

```env
HERMES_OPERATIONAL_WORKER_REQUIRED=true
HERMES_OPERATIONAL_WORKER_STALE_SECONDS=120
```

Then `/ready` fails closed when no healthy worker heartbeat is present. Inspect `/v1/operational/health` for worker count, freshness and last task/event activity. Keep the flag false for API-only development and unit tests.
