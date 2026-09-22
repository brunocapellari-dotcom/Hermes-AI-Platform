# Hermes Tool Evaluation

Decision categories: **ADOPT**, **ADOPT PATTERN**, **PRIMARY CANDIDATE**, **BENCHMARK**, **RESERVE**, **REJECT**. A tool becomes production-operational only after objective repository and live evidence. Similar products are not installed in parallel unless they cover materially different failure modes.

Last architecture review: 2026-09-22.

| Responsibility | Decision | Tool | Canonical Hermes owner | Rationale |
|---|---|---|---|---|
| model/provider gateway | ADOPT | LiteLLM 1.101.x | ModelGateway | mature active multi-provider gateway; non-enterprise core MIT; Hermes contract remains the boundary |
| agent capability library | ADOPT PATTERN / BENCHMARK | Pydantic AI v2.47.0 + official Harness | Agent/Skill Factory + Context/Tool/Security layers | selectively reuse mature capability contracts while Hermes keeps authority/state ownership |
| durable execution | BENCHMARK | DBOS 2.31.x / 3.x migration track | Hermes Durable Engine | current implementation candidate; must pass neutral crash/idempotency/version benchmark |
| durable execution | BENCHMARK | Temporal Python SDK | Hermes Durable Engine | mature replay/versioning and multi-language control plane; operational overhead must be measured |
| durable execution | BENCHMARK | Restate Python SDK 1.x | Hermes Durable Engine | durable services/workflows, exactly-once-per-ID patterns and Pydantic AI integration merit equal benchmark |
| operational schema migrations | ADOPT | Alembic | Database migration boundary | explicit versioned migrations; runtime processes do not perform DDL |
| policy authorization | ADOPT | OPA | PolicyEngine | deterministic policy outside model prompts, fail closed |
| relationship authorization | ADOPT | OpenFGA | PolicyEngine | subject-relation-object authorization complements OPA |
| MCP runtime/isolation | BENCHMARK | ToolHive 0.51.0 | Hermes MCP Gateway | evaluate permission profiles, SPIFFE JWT-SVID auth, signed artifacts, registry and Virtual MCP; security-advisory regressions remain mandatory |
| MCP federation/A2A/plugins | BENCHMARK | IBM ContextForge 1.0.7-20260921 | Hermes MCP Gateway | active Apache-2.0 option for federation/A2A/plugin hooks; never create second canonical registry/RBAC/policy authority |
| telemetry standard | ADOPT | OpenTelemetry | Hermes OTel | vendor-neutral tracing/metrics; canonical telemetry interface |
| AI observability backend | ADOPT OPTIONAL BACKEND | Langfuse 4.41.x | Hermes OTel | preferred backend: native OTLP/HTTP ingestion, strong self-host/GCP support, datasets/evals and MIT core; not operational source of truth |
| alternate AI observability backend | RESERVE | Arize Phoenix | Hermes OTel | strong OTel/eval alternative but overlaps Langfuse and uses Elastic License 2.0; do not deploy both by default |
| LLM regression/red-team | ADOPT WHEN LIVE TARGET EXISTS | Promptfoo | Hermes Evaluation | primary declarative CI regression and adversarial testing |
| Python-specific LLM assertions | RESERVE | DeepEval | Hermes Evaluation | add only for Python-native component tests or metrics not already covered |
| RAG evaluation | ADOPT WHEN RAG LIVE | Ragas | Hermes Evaluation | specialist retrieval/faithfulness/context evaluation for Second Brain/RAG paths |
| specialized LLM vulnerability scanning | RESERVE | NVIDIA Garak | Hermes Security Lab | deeper scanner cases complementary to Promptfoo |
| local GPU serving | PRIMARY CANDIDATE | vLLM | Model serving adapter | promote only by hardware/model throughput/latency/quality benchmark |
| local CPU/edge inference | PRIMARY CANDIDATE | llama.cpp | Model serving adapter | lightweight local inference; promote by real hardware benchmark |
| alternative GPU/multimodal serving | BENCHMARK | SGLang | Model serving adapter | use only if it materially beats the primary candidate |
| restricted tool orchestration | BENCHMARK | Pydantic Monty v1.0.0-beta.2 / Code Mode | Hermes Tool Orchestration | no filesystem/network/env by default; benchmark context/cost gains before direct dependency |
| OS-level code sandbox | BENCHMARK | E2B | Hermes Sandbox Service | Apache-2.0, active, GCP self-host/BYOC and isolated sandboxes; benchmark against nsjail |
| lightweight OS sandbox | BENCHMARK | nsjail 3.6 | Hermes Sandbox Service | Linux namespaces/cgroups/seccomp option for controlled hosts |
| abandoned sandbox | REJECT | Daytona OSS | Hermes Sandbox Service | repository explicitly unmaintained since June 2026 |
| alternate model gateway | BENCHMARK | Bifrost 1.7.x | ModelGateway | Apache-2.0 high-performance candidate; replace LiteLLM only after the canonical gateway benchmark shows net advantage |
| agentic LLM/MCP/A2A data plane | BENCHMARK | agentgateway 1.5.x | Hermes Agentic Data Plane | Linux Foundation Apache-2.0 candidate for consolidation; not a second default model gateway and cannot replace Hermes policy authority |
| archived LLMOps gateway | REJECT | TensorZero | ModelGateway | upstream archived in June 2026; do not add archived runtime dependencies |
| redundant LLM observability gateway | REJECT | Helicone | Hermes OTel | overlaps the selected OpenTelemetry + Langfuse stack without a distinct required failure mode |
| legacy prompt guard | REJECT | ProtectAI LLM Guard | Hermes Security | upstream archived; do not add an archived core dependency |

## Pydantic AI Harness adoption rule

Harness capabilities are treated as decomposable references. Coder and Researcher are not imported wholesale into production. In particular, unrestricted host shell execution is incompatible with Hermes production policy. The canonical mapping is stored in src/hermes/architecture_policy.py.

High-value patterns to absorb into Hermes:
- workspace-scoped FileSystem and repository context;
- bounded/allowlisted/sandboxed Shell;
- progressive skill disclosure;
- Planning/SubAgents with Hermes Task DAG and Agent Router remaining authoritative;
- Tool Search, Compaction and Tool Output Limits for context efficiency;
- Guardrails and Prompt Injection Defender as signals behind deterministic policy;
- Spend Limits integrated with the Hermes usage ledger;
- Tool Approval integrated with owner-approval policy;
- Trajectory Judge as a benchmarked long-mission evaluator;
- Capability Creation only through sandbox -> tests -> benchmark -> security -> independent audit -> registry.

Explicitly non-canonical:
- Harness Memory cannot replace the Second Brain or mission/registry stores.
- Harness Step Persistence cannot become a second durable state store.
- Dynamic Workflow cannot bypass Hermes mission state, policy or durable execution.

## Model gateway selection rule

LiteLLM is the current canonical gateway adapter target. Bifrost is the only direct replacement benchmark. Both must run the same fixtures in src/hermes/model_gateway_benchmark.py for provider compatibility, fallback/retry, streaming, structured output, tool metadata, multimodal routes, service authentication, usage/cache accounting, OpenTelemetry, overload/backpressure, latency overhead and failure isolation.

Agentgateway is evaluated for a different question: whether one agentic data plane can simplify LLM + MCP + A2A connectivity without duplicating Hermes authorization, registries and observability. It is not promoted merely because it can proxy LLM traffic.

## Durable execution selection rule

No durable engine is selected merely because an implementation already exists. DBOS, Temporal and Restate must execute the same scenarios from src/hermes/durable_benchmark.py.

Required scenarios include crash/resume, no duplicate external side effect, parallel fan-out/join, signal/wait, version upgrade, queue backpressure, long idle wait, OpenTelemetry correlation, local reproducibility and operator recovery.

DBOS remains the current reference implementation in the branch only because it was implemented first. That is not an architecture lock.

## MCP selection rule

Hermes keeps one canonical MCP control boundary. ToolHive and ContextForge are benchmark inputs/components.

From ToolHive, Hermes directly adopts the useful concepts of deny-by-default runtime permissions and artifact provenance in MCPWorkloadPolicy. ToolHive runtime itself must pass security-advisory regressions before production promotion. Agentgateway is evaluated separately as a broader agentic data plane because it spans LLM, MCP and A2A traffic; it must not create a parallel policy/registry authority.

ContextForge is evaluated for federation, A2A and plugin-hook semantics. Its registry, RBAC and policy capabilities must not duplicate Hermes Registry + OPA + OpenFGA unless a benchmark demonstrates a missing requirement that cannot be supplied through a smaller adapter.

## Evaluation selection rule

- Promptfoo: primary endpoint-level regression and red team.
- DeepEval: Python-specific assertions only when there is a concrete gap.
- Ragas: RAG-specific retrieval/generation evaluation only.
- Deterministic Hermes tests remain mandatory and cannot be replaced by LLM judges.
- Model judges/trajectory judges may supplement gates, never override deterministic security or authorization failures.

## Observability selection rule

OpenTelemetry is canonical. Langfuse is the preferred optional AI-observability backend because its core is MIT-licensed, it accepts OTLP/HTTP traces directly, has active GCP/Kubernetes self-hosting support and covers tracing, datasets and evaluations. PostgreSQL usage/audit ledgers remain canonical operational evidence. Phoenix is retained only as a benchmark/reserve alternative; never deploy both without a documented need.

## Anti-sprawl rules

1. Hermes owns the contracts and authority; tools are replaceable components.
2. One canonical owner per responsibility.
3. A benchmark candidate is not a runtime dependency by default.
4. A second framework is admitted only for a materially distinct failure mode or measurable advantage.
5. Memory, workflow state, registry, policy and telemetry ownership may not silently fork across frameworks.
6. Components capable of self-extension or shell/browser execution are least-privilege and sandboxed by default.
7. Security classifier output is evidence, never authorization.
8. New dependencies must pass supply-chain, license, maintenance and adversarial tests before promotion.
