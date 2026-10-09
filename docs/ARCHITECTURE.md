# Hermes AI Platform — canonical architecture

## Boundaries

- **Hermes:** intelligence, routing, planning, interpretation and controlled execution.
- **AI-Holding:** portfolio authority, governance, approvals, PMO and operational truth.
- **Second Brain:** institutional knowledge and temporal evidence.
- **Research AI:** web/GitHub/paper/API/dataset research and acquisition.
- **Projects:** domain execution.

Hermes owns stable interfaces, not every implementation. External frameworks are replaceable adapters.

## Core contracts

`ModelGateway`, `ProjectAdapter`, `KnowledgeProvider`, `ResearchProvider`, `MissionStore`, `AuditSink`, and `PolicyEngine` are the dependency boundaries.

## Request path

Owner -> Intent Engine -> Goal/Capability interpretation -> Project Router -> Context/Knowledge -> Knowledge Gap -> Research when required -> Task DAG -> Policy -> Tool/Project adapters -> persistence/audit -> result.

## Operational state

PostgreSQL stores Hermes mission state, registries, audit and usage/FinOps records. `WorldState` is a generated operational view and never replaces original project, Holding, knowledge or research sources.

## Production target

Google Cloud Run + Cloud SQL PostgreSQL + Secret Manager + Artifact Registry + BigQuery telemetry. Cloud SQL uses private IP through a dedicated VPC/private service connection. Cloud Run uses Direct VPC access. BigQuery is analytical; PostgreSQL stores operational mission state. No raw secret is passed to a model.

Terraform intentionally defaults `runtime_enabled=false`: the first apply can create network/database/secret containers without embedding secret values in Terraform state. Runtime deployment is enabled only after the pinned secret versions are populated through an authorized secret-management path.

## Model gateway and agentic data plane

LiteLLM is the adopted primary multi-provider model gateway behind the Hermes ModelGateway contract. Bifrost remains the only direct replacement benchmark and must run the same scenarios in src/hermes/model_gateway_benchmark.py before any switch.

Agentgateway is not treated as a second ordinary model gateway. It is a benchmark candidate for a broader agentic data plane spanning LLM, MCP and A2A traffic. Promotion requires measurable consolidation value while Hermes retains OPA/OpenFGA authority and canonical registries.

TensorZero is rejected because its upstream repository is archived. Helicone is rejected from the Hermes stack because its observability responsibility duplicates OpenTelemetry + Langfuse.

## Durable work

Hermes MissionStore remains canonical at the mission layer. No durable engine is permanently selected yet.

DBOS, Temporal and Restate are equal benchmark candidates behind a Hermes-owned durable boundary. The existing DBOS worker/dispatcher is the current reference implementation only because it was implemented first; it is not an architecture lock.

All candidates must pass the same crash/resume, no-duplicate-side-effect, parallel DAG, signal/wait, version-upgrade, queue/backpressure, long-idle, OpenTelemetry, local reproducibility and operator-recovery scenarios defined in src/hermes/durable_benchmark.py. Only one engine becomes canonical after measured evidence.

## Observability

OpenTelemetry is canonical for distributed telemetry. Hermes will follow GenAI semantic conventions where stable, but wraps them to avoid schema lock-in. PostgreSQL usage/audit events remain canonical operational evidence; Prometheus exposes service metrics; BigQuery is the analytical destination in GCP.

Langfuse is the preferred optional AI-observability backend over OpenTelemetry. It may provide trace exploration, datasets, experiments and evaluation workflows, but it never becomes mission state, policy authority, FinOps source of truth or a required runtime dependency. Phoenix remains a reserve alternative and is not deployed in parallel by default.

## Agent frameworks and capability libraries

Hermes is the platform. LangGraph, Pydantic AI and Pydantic AI Harness are components/reference implementations.

Pydantic AI v2.47.0 and its official Harness are audited capability-by-capability. Hermes adopts useful semantics such as scoped FileSystem/Shell, Repo Context, Planning, SubAgents, Code Mode, Tool Search, Compaction, Tool Output Limits, cache-efficiency monitoring, Guardrails, Spend Limits, Tool Approval and OpenTelemetry while keeping canonical memory, durable state, policy, registry and authority inside Hermes/Second Brain.

Restricted model-written orchestration uses the Hermes CodeModeRuntime boundary; Pydantic Monty is the current benchmark candidate. Arbitrary coding/build execution uses a separate SandboxExecutor service benchmarked across E2B and nsjail, with gVisor reserved for GKE/container isolation. Daytona OSS is rejected because its public repository is no longer maintained.

Coder and Researcher are decomposed rather than imported wholesale for production. In particular, production command execution must remain sandboxed and policy-bound.

The canonical capability decisions live in src/hermes/architecture_policy.py and the detailed review in docs/PYDANTIC_AI_HARNESS_AUDIT.md.

## MCP runtime and federation

Hermes MCP Gateway remains the single canonical MCP admission/control boundary.

ToolHive is benchmarked for secure runtime isolation, permission profiles, signed artifact provenance, registry and Virtual MCP capabilities. Hermes already adopted the portable permission/provenance concept in MCPWorkloadPolicy without adopting ToolHive as the control plane.

IBM ContextForge is benchmarked for federation, A2A and plugin-hook semantics. Its registry/RBAC/policy functions must not duplicate Hermes Registry + OPA + OpenFGA unless a measured missing requirement justifies a narrow adapter.

## Evaluation architecture

Hermes deterministic tests remain mandatory.

Promptfoo owns endpoint regression and red-team testing. Ragas owns RAG-specific retrieval/context/faithfulness evaluation. DeepEval is optional for Python-specific LLM assertions that are not already covered. Trajectory Judge remains a benchmark capability for long missions.

The routing is executable in src/hermes/evaluation_strategy.py so multiple frameworks do not silently test the same responsibility.


## Release integrity

A production release is identified by an immutable Hermes version/commit. Runtime, migration jobs and durable benchmark resources may not be enabled in Terraform without this identity.

The dependency graph must eventually be frozen with a generated uv.lock. A hand-authored lock file is not acceptable. Until a working executor can generate and verify the lock, broad dependency resolution remains an explicit release-readiness gap.

## Approval and self-extension

Sensitive tool actions may require a persistent one-time approval. Approval scope is actor + action + resource + payload hash with TTL and compare-and-set consumption. A hard policy denial remains non-approvable.

Agent/skill replacement and rollback are non-destructive and transactional. Controlled self-improvement stage transitions use compare-and-set semantics. Self-generated capabilities never self-promote.
