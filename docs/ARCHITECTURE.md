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

## Model gateway

Primary candidate: LiteLLM behind the Hermes `ModelGateway` contract. Bifrost and agentgateway are benchmark alternatives, not second concurrent gateways. Agentgateway must pass the Hermes Security Test Lab before promotion because its project disclosed multiple 2026 advisories involving MCP authorization/routing/sanitization.

## Durable work

Hermes MissionStore remains canonical at the mission layer. No durable engine is permanently selected yet.

DBOS, Temporal and Restate are equal benchmark candidates behind a Hermes-owned durable boundary. The existing DBOS worker/dispatcher is the current reference implementation only because it was implemented first; it is not an architecture lock.

All candidates must pass the same crash/resume, no-duplicate-side-effect, parallel DAG, signal/wait, version-upgrade, queue/backpressure, long-idle, OpenTelemetry, local reproducibility and operator-recovery scenarios defined in src/hermes/durable_benchmark.py. Only one engine becomes canonical after measured evidence.

## Observability

OpenTelemetry is canonical for distributed telemetry. Hermes will follow GenAI semantic conventions where stable, but wraps them to avoid schema lock-in. PostgreSQL usage/audit events remain canonical operational evidence; Prometheus exposes service metrics; BigQuery is the analytical destination in GCP.

Arize Phoenix is the preferred optional AI-observability backend/UI over OpenTelemetry. Phoenix may provide trace exploration, datasets and evaluation workflows, but it never becomes mission state, policy authority, FinOps source of truth or a required runtime dependency.

## Agent frameworks and capability libraries

Hermes is the platform. LangGraph, Pydantic AI and Pydantic AI Harness are components/reference implementations.

Pydantic AI Harness is audited capability-by-capability. Hermes may adopt patterns such as scoped FileSystem, bounded Shell, RepoContext, Planning, SubAgents, Tool Search, Compaction, Tool Output Limits, Guardrails, Spend Limits, Tool Approval and OpenTelemetry. It does not delegate canonical memory, durable state, policy, registry or authority to the Harness.

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
