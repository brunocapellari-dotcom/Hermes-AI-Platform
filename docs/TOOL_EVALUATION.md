# Hermes Tool Evaluation

Decision categories: **ADOPT**, **ADOPT PATTERN**, **PRIMARY CANDIDATE**, **BENCHMARK**, **RESERVE**, **REJECT**. A tool becomes production-operational only after objective repository and live evidence. Similar products are not installed in parallel unless they cover materially different failure modes.

Last architecture review: 2026-09-21.

| Responsibility | Decision | Tool | Canonical Hermes owner | Rationale |
|---|---|---|---|---|
| model/provider gateway | ADOPT | LiteLLM | ModelGateway | provider abstraction remains behind Hermes contract; no second gateway by default |
| agent capability library | ADOPT PATTERN / BENCHMARK | Pydantic AI Harness 0.32.x | Agent/Skill Factory + Context/Tool/Security layers | selectively reuse capability ideas; Harness is not Hermes and 0.x APIs may move |
| durable execution | BENCHMARK | DBOS 2.31.x / 3.x migration track | Hermes Durable Engine | current implementation candidate; must pass neutral crash/idempotency/version benchmark |
| durable execution | BENCHMARK | Temporal Python SDK | Hermes Durable Engine | mature replay/versioning and multi-language control plane; operational overhead must be measured |
| durable execution | BENCHMARK | Restate Python SDK 1.x | Hermes Durable Engine | durable services/workflows, exactly-once-per-ID patterns and Pydantic AI integration merit equal benchmark |
| operational schema migrations | ADOPT | Alembic | Database migration boundary | explicit versioned migrations; runtime processes do not perform DDL |
| policy authorization | ADOPT | OPA | PolicyEngine | deterministic policy outside model prompts, fail closed |
| relationship authorization | ADOPT | OpenFGA | PolicyEngine | subject-relation-object authorization complements OPA |
| MCP runtime/isolation | BENCHMARK | ToolHive 0.50.x | Hermes MCP Gateway | evaluate permission profiles, signed artifacts, registry, virtual MCP and isolated runtime; recent security fixes require regression tests |
| MCP federation/A2A/plugins | BENCHMARK | IBM ContextForge 1.0.x | Hermes MCP Gateway | use only if federation/A2A/plugin hooks add measurable value; never create second canonical registry/RBAC/policy authority |
| telemetry standard | ADOPT | OpenTelemetry | Hermes OTel | vendor-neutral tracing/metrics; canonical telemetry interface |
| AI observability backend | ADOPT OPTIONAL BACKEND | Arize Phoenix 20.x | Hermes OTel | preferred trace/eval UI over OTel; not operational source of truth and not a replacement for Hermes ledger |
| LLM regression/red-team | ADOPT WHEN LIVE TARGET EXISTS | Promptfoo | Hermes Evaluation | primary declarative CI regression and adversarial testing |
| Python-specific LLM assertions | RESERVE | DeepEval | Hermes Evaluation | add only for Python-native component tests or metrics not already covered |
| RAG evaluation | ADOPT WHEN RAG LIVE | Ragas | Hermes Evaluation | specialist retrieval/faithfulness/context evaluation for Second Brain/RAG paths |
| specialized LLM vulnerability scanning | RESERVE | NVIDIA Garak | Hermes Security Lab | deeper scanner cases complementary to Promptfoo |
| local GPU serving | PRIMARY CANDIDATE | vLLM | Model serving adapter | promote only by hardware/model throughput/latency/quality benchmark |
| local CPU/edge inference | PRIMARY CANDIDATE | llama.cpp | Model serving adapter | lightweight local inference; promote by real hardware benchmark |
| alternative GPU/multimodal serving | BENCHMARK | SGLang | Model serving adapter | use only if it materially beats the primary candidate |
| alternate model gateway | BENCHMARK | Bifrost / agentgateway | ModelGateway | consider only if measured benefits exceed migration and security cost |
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

## Durable execution selection rule

No durable engine is selected merely because an implementation already exists. DBOS, Temporal and Restate must execute the same scenarios from src/hermes/durable_benchmark.py.

Required scenarios include crash/resume, no duplicate external side effect, parallel fan-out/join, signal/wait, version upgrade, queue backpressure, long idle wait, OpenTelemetry correlation, local reproducibility and operator recovery.

DBOS remains the current reference implementation in the branch only because it was implemented first. That is not an architecture lock.

## MCP selection rule

Hermes keeps one canonical MCP control boundary. ToolHive and ContextForge are benchmark inputs/components.

From ToolHive, Hermes directly adopts the useful concepts of deny-by-default runtime permissions and artifact provenance in MCPWorkloadPolicy. ToolHive runtime itself must pass security-advisory regressions before production promotion.

ContextForge is evaluated for federation, A2A and plugin-hook semantics. Its registry, RBAC and policy capabilities must not duplicate Hermes Registry + OPA + OpenFGA unless a benchmark demonstrates a missing requirement that cannot be supplied through a smaller adapter.

## Evaluation selection rule

- Promptfoo: primary endpoint-level regression and red team.
- DeepEval: Python-specific assertions only when there is a concrete gap.
- Ragas: RAG-specific retrieval/generation evaluation only.
- Deterministic Hermes tests remain mandatory and cannot be replaced by LLM judges.
- Model judges/trajectory judges may supplement gates, never override deterministic security or authorization failures.

## Observability selection rule

OpenTelemetry is canonical. Phoenix is the preferred optional AI-observability backend/viewer because it can consume trace data without changing Hermes state ownership. PostgreSQL usage/audit ledgers remain canonical operational evidence; Phoenix must never become a second source of truth.

## Anti-sprawl rules

1. Hermes owns the contracts and authority; tools are replaceable components.
2. One canonical owner per responsibility.
3. A benchmark candidate is not a runtime dependency by default.
4. A second framework is admitted only for a materially distinct failure mode or measurable advantage.
5. Memory, workflow state, registry, policy and telemetry ownership may not silently fork across frameworks.
6. Components capable of self-extension or shell/browser execution are least-privilege and sandboxed by default.
7. Security classifier output is evidence, never authorization.
8. New dependencies must pass supply-chain, license, maintenance and adversarial tests before promotion.
