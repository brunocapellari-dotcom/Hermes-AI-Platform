# Pydantic AI / official Harness audit for Hermes

Date: 2026-09-22
Reference reviewed: Pydantic AI v2.47.0 and its official Harness capability catalog.

## Decision

Pydantic AI and its Harness are high-value component/reference libraries. They do not replace Hermes orchestration, mission state, policy, knowledge, registry, model routing, durable-engine selection or project authority.

Hermes adopts useful semantics behind Hermes-owned contracts. Direct dependencies are added only when the upstream implementation is complex enough to justify the supply-chain/runtime cost.

## Capability matrix

| Capability | Hermes decision | Canonical owner | Current Hermes treatment |
|---|---|---|---|
| Coder | ADOPT PATTERN | Agent Factory + Tool/Sandbox boundary | decomposed; WorkspaceFileSystem and sandbox executor contract implemented |
| Researcher | ADOPT PATTERN | Research AI | bounded/delegated research patterns only |
| FileSystem | ADOPT PATTERN | Tool Gateway | root confinement, protected paths, symlink/traversal protection, atomic hash-aware writes implemented |
| Shell | ADOPT PATTERN | Tool/Sandbox boundary | explicit allowlist/policy and SandboxExecutor contract; no host subprocess fallback |
| Repo Context | ADOPT PATTERN | Context Router | repository guidance remains derived run context, not memory |
| Memory | REJECT AS CANONICAL | Second Brain | no second canonical memory store |
| Conversation Search | RESERVE | Context Router | only when persisted conversation retrieval has measured value |
| Skills | ADOPT PATTERN | Skill Factory/Registry | progressive disclosure compatible with Hermes-governed skill lifecycle |
| Planning | ADOPT PATTERN | Task DAG Planner | model may propose; Hermes validates/persists DAG |
| SubAgents | ADOPT PATTERN | Agent Router/Factory | registry-backed, least privilege and bounded delegation |
| Dynamic Workflow | BENCHMARK | Task DAG Planner | cannot bypass durable mission state or child-call budgets |
| Advisor | ADOPT PATTERN | Review Panel/Model Router | stronger-model consultation without separate authority |
| Code Mode | BENCHMARK | Tool Orchestration | vendor-neutral CodeModeService implemented; Monty is current runtime candidate |
| Tool Search | ADOPT PATTERN | Tool Registry | native lazy tool search implemented |
| Compaction | ADOPT PATTERN | Context Router | transparent deterministic compaction implemented; canonical evidence unchanged |
| Tool Output Limits | ADOPT PATTERN | Tool Gateway | native result bounding implemented |
| Warn On Cache Busts | ADOPT PATTERN | Context/FinOps | provider cache-token accounting and cache-efficiency diagnostics implemented |
| System Reminders | ADOPT PATTERN | Context Router | reserve for long-run instruction reinforcement; no policy authority |
| Browser capabilities | RESERVE | Research AI | browser execution remains isolated from Hermes core |
| Guardrails | ADOPT PATTERN | Security/Privacy | supplemental validators only; deterministic policy remains authority |
| Prompt Injection Defender | BENCHMARK | Security | signal only, never authorization |
| Spend Limits | ADOPT PATTERN | Budget Guard | persistent daily/weekly/monthly limits implemented |
| Tool Approval | ADOPT PATTERN | Policy Engine | persistent TTL, payload-hash-bound, one-time approval implemented |
| Trajectory Judge | BENCHMARK | Evaluation | require measured long-run benefit before promotion |
| Capability Creation | BENCHMARK RESTRICTED | Agent/Skill Factory | proposal only; sandbox/tests/benchmark/security/independent audit required |
| Step Persistence | REJECT AS CANONICAL | Durable Engine | would duplicate durable workflow state |
| OpenTelemetry | ADOPT | Hermes OTel | canonical distributed telemetry |

## Coder boundary

The current official Harness itself has materially improved FileSystem/Shell controls: traversal/symlink safety, allow/deny execution controls, timeouts and credential stripping. Hermes still does not import the complete Coder as its production authority because authorization, approvals, durable state and repository lifecycle must remain Hermes-owned.

Hermes Coder execution is split into two security levels:

1. **Restricted orchestration code** — Code Mode runtime such as Monty. Model-written Python has no filesystem, environment or network unless explicitly bridged. Any external tool call must traverse Hermes ToolGateway.
2. **OS-level coding work** — separate SandboxExecutor service such as E2B or nsjail after the sandbox benchmark. It never runs untrusted code inside the Hermes API process.

The host shell is never a production fallback.

## Code Mode / Monty

Pydantic Monty is a distinct candidate from an OS sandbox. It is a Rust Python interpreter designed for AI-written code, with no filesystem/network/environment by default and built-in resource limits/snapshots.

Hermes has implemented a vendor-neutral CodeModeRuntime contract. A runtime may invoke only request-allowlisted tool IDs, with a hard call budget, and every invocation still passes through ToolGateway policy, approval, rate limit and timeout.

Monty remains BENCHMARK until its current v1 beta line and Hermes integration pass deterministic security/performance tests. It cannot replace E2B/nsjail for arbitrary repository builds or system tooling.

## Researcher decomposition

Research AI remains the shared research service. Useful upstream patterns are bounded output, sub-question delegation, lazy capability/tool loading, citation/evidence handoff and hard child-agent limits. Research findings remain non-canonical until Knowledge Factory/Second Brain validation.

## Context controls

Hermes now implements:
- lazy tool search;
- output bounds;
- policy-filtered deterministic context compaction;
- prompt-cache efficiency accounting;
- repository/workspace context boundaries.

Compacted content is derived context and may never overwrite source evidence or Second Brain claims. LLM-generated summaries may be evaluated later but are not required for canonical compaction.

## Safety and approvals

The authority chain remains:

authenticated identity -> Hermes policy -> OPA/OpenFGA -> optional one-time approval -> scoped credential -> tool/project action -> audit.

Approval is not permission escalation. A hard policy denial cannot be converted into an allowed action merely by obtaining an approval. Approval records store payload hashes, not raw sensitive payloads, and are one-time/TTL-bound.

## Self-extension

Capability Creation is allowed only as a proposal mechanism:

need -> typed spec -> least privilege -> sandbox -> deterministic tests -> benchmark -> adversarial/security tests -> independent auditor -> registry.

The creator cannot approve its own capability, self-grant scopes, or directly deploy production code.

## Durability

Harness Step Persistence is not production workflow truth. DBOS, Temporal and Restate remain the canonical durable-engine benchmark candidates. Pydantic AI's additional integrations such as Prefect are RESERVE unless the three-candidate benchmark reveals an unmet requirement.

## Dependency policy

Do not add Pydantic AI/Harness/Monty merely to obtain behavior that Hermes can implement safely in a small stable contract.

Direct adoption requires:
- a capability whose implementation complexity justifies the dependency;
- a pinned/locked version;
- supply-chain/license review;
- deterministic regression coverage;
- no duplicate canonical state or authority.
