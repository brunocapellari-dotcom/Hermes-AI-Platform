# Pydantic AI Harness audit for Hermes

Date: 2026-09-21
Reference version reviewed: Pydantic AI Harness 0.32.x.

## Decision

Pydantic AI Harness is useful as a decomposable capability/reference library. It does not replace Hermes orchestration, state, policy, knowledge, registry, agent factory, skill factory, model routing or durable execution.

The package is still on 0.x versioning. Production adoption is therefore capability-by-capability and behind Hermes contracts.

## Capability matrix

| Capability | Hermes decision | Canonical owner | Integration rule |
|---|---|---|---|
| Coder | ADOPT PATTERN | Agent Factory + Tool Gateway | never use unrestricted host shell in production; compose safer internal coder |
| Researcher | ADOPT PATTERN | Research AI | reuse bounded output/delegation; do not duplicate Research AI |
| FileSystem | ADOPT PATTERN | Tool Gateway | workspace root, protected paths, audited writes |
| Shell | ADOPT PATTERN | Tool Gateway | sandbox, explicit commands, timeout, credential stripping, approval |
| RepoContext | ADOPT PATTERN | Context Router | load repository guidance and structure on demand |
| Memory | REJECT AS CANONICAL | Second Brain | scratch/session cache only; no second truth store |
| Conversation Search | RESERVE | Context Router | use only when indexed conversation history materially improves retrieval |
| Skills | ADOPT PATTERN | Skill Factory/Registry | progressive disclosure and SKILL.md compatibility through Hermes governance |
| Planning | ADOPT PATTERN | Task DAG Planner | model proposes; Hermes validates and persists authoritative DAG |
| SubAgents | ADOPT PATTERN | Agent Router/Factory | registry-backed, bounded permissions, own lifecycle only when justified |
| Dynamic Workflow | BENCHMARK | Task DAG Planner | bounded fan-out/chain/vote; cannot bypass mission/durable state |
| Advisor | ADOPT PATTERN | Review Panel/Model Router | escalate selected decisions to stronger model without creating another agent class |
| Tool Search | ADOPT PATTERN | Tool Registry | lazy tool discovery to reduce prompt/tool schema load |
| Compaction | ADOPT PATTERN | Context Router | compressed context is derived state, never canonical memory |
| Tool Output Limits | ADOPT PATTERN | Tool Gateway | cap/truncate/spill/summarize before model ingestion |
| Playwright Browser | RESERVE | Research AI | deterministic browser automation for research/test workflows |
| Browser Use | RESERVE | Research AI | autonomous browser only with sandbox, policy and approval |
| Guardrails | ADOPT PATTERN | Security/Privacy | validators complement OPA/OpenFGA; never become authority |
| Prompt Injection Defender | BENCHMARK | Security | detector signal only; classifier cannot grant permission |
| Spend Limits | ADOPT PATTERN | Budget Guard | integrate with Hermes persistent usage/cost ledger |
| Tool Approval | ADOPT PATTERN | Policy Engine | map deferred calls to owner-approval boundary |
| Trajectory Judge | BENCHMARK | Evaluation | test long-run steering benefit, false positives, cost and latency |
| Capability Creation | BENCHMARK RESTRICTED | Agent/Skill Factory | generated capability enters sandbox only; no self-registration to production |
| Step Persistence | REJECT AS CANONICAL | Durable Engine | avoid duplicate checkpoints/workflow state |
| OpenTelemetry instrumentation | ADOPT | Hermes OTel | standard trace/metric propagation |

## Coder decomposition

The full Coder harness is not production-safe as-is for Hermes because its documented default shell composition is unrestricted on the host. Hermes will construct a safer internal coding capability from:

1. repository-scoped file access;
2. protected secret/repository metadata paths;
3. content/hash-aware edits where practical;
4. allowlisted or sandboxed command execution;
5. process timeout and output bounds;
6. credential stripping;
7. egress policy;
8. Tool Gateway authorization and audit;
9. explicit approval for high-risk writes;
10. deterministic tests before any promotion.

This makes the useful behavior portable without making Pydantic AI Harness the security boundary.

## Researcher decomposition

Research AI remains the shared research service. Useful patterns to absorb are:

- bounded page/tool output;
- sub-question delegation;
- context-efficient tool discovery;
- citation/evidence handoff;
- hard maximum child-agent calls;
- isolation of research findings from authoritative knowledge until Knowledge Factory validation.

## Context controls

Hermes should implement or adapt the following capability semantics centrally:

- lazy tool loading;
- tool output limits;
- context compaction;
- conversation/history retrieval when available;
- repository context;
- cache-safe reminders only where necessary.

All compacted/summarized content is derived context. It may never overwrite evidence, source documents or canonical Second Brain claims.

## Safety controls

Harness Guardrails and Prompt Injection Defender can supply signals, but the authority chain remains:

identity -> Hermes policy -> OPA/OpenFGA -> scoped credentials -> tool/project action -> audit.

Spend limits never override hard policy. Tool approvals never grant rights outside the caller's maximum authorization envelope.

## Self-extension

Capability Creation is allowed only as a proposal mechanism:

need -> typed specification -> least-privilege permissions -> sandbox -> deterministic tests -> benchmark -> security/adversarial tests -> independent auditor -> registry.

The creating agent cannot approve its own capability, expand its own scopes or deploy production code.

## Durability

Harness Step Persistence is not used as the production source of workflow state. Durable execution is selected separately through the DBOS/Temporal/Restate benchmark. This avoids split recovery state and inconsistent checkpoints.

## Dependency policy

Do not add pydantic-ai-harness to Hermes core dependencies merely to gain one capability. Prefer:

- internal implementation when small and stable;
- a narrow optional adapter when the upstream capability is complex and useful;
- no dependency when Hermes already owns the responsibility.

Any direct Harness dependency must be version-pinned, supply-chain scanned and accompanied by a regression test for the exact capability being used.
