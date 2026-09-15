# Tool evaluation — 2026-09-15

## Decisions

### LiteLLM — ADOPT behind ModelGateway
Broad provider coverage, OpenAI-compatible API, routing/fallback/cost controls and multi-provider support. Do not depend on commercial-only features. Pin releases and keep Hermes contracts provider-neutral.

### Bifrost — BENCHMARK
High-performance Go gateway and useful alternative. Do not run concurrently with LiteLLM by default. Promote only if Hermes benchmarks show material latency/throughput/reliability advantage for our workload with compatible licensing/features.

### agentgateway — BENCHMARK, SECURITY GATE REQUIRED
Attractive consolidation candidate for LLM, MCP and A2A traffic with RBAC/OAuth/OpenTelemetry. It could reduce gateway sprawl. Do not promote solely from project-authored speed benchmarks: 2026 security advisories covered cross-route stateful MCP authorization, cross-namespace backend authorization and MCP/OpenAPI parameter sanitization. Hermes adversarial tests are mandatory before any replacement decision.

### LangGraph — RESERVE/COMPONENT
Strong stateful/durable agent graph features. Hermes owns independent mission state and durable workflow boundaries, so LangGraph is not the global source of truth.

### PydanticAI — RESERVE/COMPONENT
Good typed Python agent ergonomics. Prefer for narrow agent implementations when it reduces code; do not couple registries, permissions, memory or missions to it.

### DBOS — ADOPT AS PRIMARY DURABLE EXECUTION CANDIDATE
MIT Python library with Postgres-backed workflows, queues, retries, recovery, deduplication, scheduling and external client. Reuses Cloud SQL instead of introducing a separate workflow server. Hermes MissionStore remains canonical and DBOS carries the durable execution record. Validate failure recovery and no-duplicate side effects before production.

### Temporal — RESERVE
Still a strong distributed durable platform. Promote over DBOS only if multi-language orchestration, operating scale, benchmark or reliability requirements justify its additional infrastructure.

### OPA + OpenFGA — ADOPT for production authorization boundary
OPA evaluates policy; OpenFGA models relationship authorization. Keep authorization outside prompts and models. Application policy guards remain fail-closed but are not the complete production authorization layer.

### Google Secret Manager — ADOPT on GCP
Avoid a second secrets platform in the first GCP production deployment. Infisical/OpenBao remain portability alternatives, not parallel secret stores.

### OpenTelemetry — ADOPT
Vendor-neutral traces/metrics/log correlation. GenAI semantic conventions cover model, agent, workflow, tool and MCP operations but remain Development, so Hermes must isolate semantic-version changes behind its telemetry adapter.

### vLLM / SGLang / llama.cpp — BENCHMARK by hardware
No permanent model/runtime lock. Hardware discovery narrows candidates; project-specific benchmarks decide.

## Anti-sprawl rules

One model gateway, one operational mission store, one durable execution backend, one portfolio authority, one canonical knowledge system, one policy decision path and one secrets authority per deployment environment.
