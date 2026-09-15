# Tool evaluation — 2026-09-15

## Decisions

### LiteLLM — ADOPT behind ModelGateway
Broad provider coverage, OpenAI-compatible API, routing/fallback/cost controls and multi-provider support. Do not depend on commercial-only features. Pin releases and keep Hermes contracts provider-neutral.

### Model Context Protocol Python SDK v2.2.0 — ADOPT AS OPTIONAL OFFICIAL MCP INTERFACE
Use the official SDK behind the Hermes MCP Security Gateway rather than inventing a second protocol implementation. v2.2.0 tightens redirect origin handling, OAuth issuer validation, token-resource validation options and session limits. Hermes remains responsible for server allowlists, schema pinning, risk classification, SSRF/egress controls and authorization. Do not let MCP content expand its own permissions.

### EleutherAI lm-evaluation-harness v0.4.13 — ADOPT FOR OFFLINE MODEL BENCHMARKING
Use for model selection and regression benchmarks, including Portuguese Bench, long-context and reasoning suites. It does not replace Hermes Evaluation Lab: lm-eval measures model capability; Hermes Evaluation Lab measures ecosystem-specific behavior, policies, golden tasks and operational acceptance.

### Presidio 2.2.364 — ADOPT AS OPTIONAL PRIVACY ENGINE
Presidio moved to the Data Privacy Stack organization and remains active. Use it behind the Hermes privacy adapter for richer PII recognition/anonymization when installed. Hermes keeps a lightweight deterministic secret/PII guard in the core so outbound safety does not disappear when the optional NLP stack is unavailable.

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
No permanent model/runtime lock. Hardware discovery narrows candidates; project-specific benchmarks decide. vLLM is the primary GPU serving candidate, llama.cpp the CPU/edge candidate, and SGLang a replacement candidate only when measured gains justify it.

### Phoenix — OPTIONAL OBSERVABILITY UI
Useful for inspecting traces/evals, but OpenTelemetry and the Hermes ledger remain canonical. Do not create a second telemetry truth source.

### Promptfoo + Garak — LIVE SECURITY/EVAL GATES
Promptfoo is suited to declarative prompt/agent regression and adversarial CI against real endpoints. Garak remains a specialized vulnerability scanner. Neither belongs in the core runtime.

### ProtectAI llm-guard — REJECT
Upstream is archived. Do not add a security-critical dependency without an actively maintained upstream.

## Hermes native capabilities added in this review

- Adaptive Model Intelligence: observed task-specific quality, reliability, latency, cost and drift influence routing without changing provider-neutral contracts.
- MCP Security Gateway: explicit server/tool allowlists, HTTPS/private-network rejection, schema pinning and mutation approval boundary.
- Sensitive Data Guard: deterministic secret and common personal-data detection/redaction before external model/tool calls; Presidio can enrich it as an optional engine.
- Deliberation Engine: deterministic multi-candidate scoring, quorum and disagreement escalation. It complements Critic/Judge/Auditor rather than replacing them.

## Anti-sprawl rules

One model gateway, one operational mission store, one durable execution backend, one portfolio authority, one canonical knowledge system, one policy decision path, one secrets authority and one MCP admission boundary per deployment environment.
