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

## Production target

Google Cloud Run + Cloud SQL PostgreSQL + Secret Manager + Artifact Registry + BigQuery telemetry. BigQuery is analytical; PostgreSQL stores operational mission state. No raw secret is passed to a model.

## Model gateway

Primary candidate: LiteLLM behind the Hermes `ModelGateway` contract. Bifrost is a benchmark alternative, not a second concurrent gateway. Local runtimes are selected by hardware/benchmark, with vLLM/SGLang for suitable GPU serving and llama.cpp for constrained local CPU use.

## Durable work

Mission state and checkpoints are canonical Hermes records. A durable workflow runtime (Temporal remains preferred) may execute long jobs, but it cannot become a competing source of truth.

## Agent frameworks

LangGraph and PydanticAI are components, not architecture. Introduce only where benchmarked value exceeds the maintenance cost. This avoids framework lock-in and duplicate state/memory.
