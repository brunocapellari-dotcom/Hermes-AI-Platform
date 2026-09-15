# Hermes Tool Evaluation

Decision categories: **ADOPT**, **PRIMARY CANDIDATE**, **BENCHMARK**, **RESERVE**, **REJECT**. A tool only becomes production-operational after objective repository and live evidence. Similar products are not installed in parallel without a demonstrated need.

| Responsibility | Decision | Tool | Rationale |
|---|---|---|---|
| model/provider gateway | ADOPT | LiteLLM | single provider abstraction, routing/cost surface; avoid a second gateway by default |
| durable execution | ADOPT | DBOS | Postgres-backed workflows/queues/recovery align with Cloud SQL and avoid another orchestration control plane |
| operational schema migrations | ADOPT | Alembic | explicit versioned migrations for Cloud SQL; production does not rely on `create_all()` |
| policy authorization | ADOPT | OPA | policy decisions remain external to model prompts and fail closed |
| relationship authorization | ADOPT | OpenFGA | explicit subject-relation-object authorization for tools/projects; complementary to OPA |
| telemetry standard | ADOPT | OpenTelemetry | common tracing/metrics interface; Hermes usage ledger remains canonical for costs and operational accounting |
| local GPU serving | PRIMARY CANDIDATE | vLLM | active high-throughput serving engine; promotion depends on real hardware/model benchmarks |
| local CPU/edge inference | PRIMARY CANDIDATE | llama.cpp | active lightweight C/C++ inference; promotion depends on real hardware/model benchmarks |
| alternative GPU/multimodal serving | BENCHMARK | SGLang | evaluate only when latency, multimodal or model support materially beats the primary serving option |
| AI observability UI | BENCHMARK | Arize Phoenix | useful optional visualization/evaluation surface; must not become a second source of truth beside OTel + Hermes ledger |
| live prompt/agent acceptance | ADOPT WHEN LIVE ENDPOINT EXISTS | Promptfoo | declarative evaluations/red-team in CI; not a runtime dependency |
| specialized LLM vulnerability scanning | RESERVE | NVIDIA Garak | complements Promptfoo for deeper scanner cases; not duplicated in every CI run |
| alternative workflow platform | RESERVE | Temporal | only if multilingual/scale/reliability needs objectively exceed DBOS/Postgres architecture |
| alternate gateway | BENCHMARK | Bifrost / agentgateway | consider only if measured benefits exceed migration/security cost; agentgateway requires adversarial security validation |
| legacy prompt guard | REJECT | ProtectAI LLM Guard | upstream repository archived; do not replace maintained Hermes controls with an archived core dependency |

## Anti-sprawl rules

1. One canonical tool per responsibility unless a benchmark proves a second tool covers a materially different failure mode.
2. Benchmarks never become runtime dependencies automatically.
3. Model serving is selected by actual hardware, throughput, latency, quality, memory and cost measurements.
4. External security tools complement — never replace — OPA/OpenFGA, scoped credentials, egress controls, audit logs and human approval boundaries.
5. Observability products may visualize OpenTelemetry, but canonical state stays in Hermes operational stores and the Holding/Second Brain according to responsibility.
