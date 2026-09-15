# Tool evaluation — 2026-09-15

## Decisions

### LiteLLM — ADOPT behind ModelGateway
Broad provider coverage, OpenAI-compatible API, routing/fallback/cost controls, MCP/A2A surfaces and published GCP deployment path. Do not depend on commercial-only features. Pin images/releases and verify signatures.

### Bifrost — BENCHMARK
High-performance Go gateway and useful alternative. Do not run concurrently with LiteLLM by default. Promote only if Hermes benchmarks show material latency/throughput/reliability advantage for our workload with compatible licensing/features.

### LangGraph — RESERVE/COMPONENT
Strong stateful/durable agent graph features. Hermes already requires independent mission state and durable workflow boundaries, so LangGraph is not the global source of truth.

### PydanticAI — RESERVE/COMPONENT
Good typed Python agent ergonomics. Prefer for narrow agent implementations when it reduces code; do not couple registries, permissions, memory or missions to it.

### Temporal — ADOPT for durable execution once wired
Use for crash-resistant long-running execution, timers, retries and resumability. Hermes Mission Store/AI-Holding authority remain canonical.

### OPA + OpenFGA — ADOPT for production authorization boundary
OPA evaluates policy; OpenFGA models relationship authorization. Keep authorization outside prompts and models.

### Google Secret Manager — ADOPT on GCP
Avoid a second secrets platform in the first GCP production deployment. Infisical/OpenBao remain portability alternatives, not parallel secret stores.

### OpenTelemetry — ADOPT
Vendor-neutral traces/metrics/log correlation. Langfuse can be attached for LLM-specific analytics only if it does not duplicate canonical telemetry.

### vLLM / SGLang / llama.cpp — BENCHMARK by hardware
No permanent model/runtime lock. Hardware discovery narrows candidates; project-specific benchmarks decide.

## Anti-sprawl rules

One model gateway, one operational mission store, one portfolio authority, one canonical knowledge system, one policy decision path and one secrets authority per deployment environment.
