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

Hermes `MissionStore` remains canonical. DBOS is the primary durable-execution candidate because it adds Postgres-backed workflows, queues, deduplication and recovery without another orchestration server. Hermes dispatches with mission ID as idempotency/deduplication identity. Temporal remains a reserve option if scale, multi-language orchestration or benchmark evidence justifies the additional control plane.

## Observability

OpenTelemetry is canonical for distributed telemetry. Hermes will follow GenAI semantic conventions where stable, but wraps them because the conventions are still marked Development. PostgreSQL usage events are the initial auditable FinOps ledger; Prometheus exposes service metrics; BigQuery is the analytical destination in GCP.

## Agent frameworks

LangGraph and PydanticAI are components, not architecture. Introduce only where benchmarked value exceeds the maintenance cost. This avoids framework lock-in and duplicate state/memory.
