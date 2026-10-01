# Hermes Engineering & Agent Platform — 2026-10-01

Status: APPROVED ARCHITECTURE ADDENDUM

## 1. Agent Manifest

Every Hermes agent must expose a typed manifest with:

- `entry`: input channels/types;
- `instructions`: mission, objectives, rules;
- `knowledge`: canonical/retrieval sources;
- `tools`: tool IDs and scopes;
- `triggers`: events/schedules/conditions;
- `limits`: forbidden actions, approvals, timeout, budget and rate limits.

The implementation contract should be Pydantic-first and generate JSON Schema 2020-12.

## 2. Engineering Factory

Canonical software-change flow:

`request -> repo reconnaissance -> Change Contract -> plan -> independent model review -> isolated worktree -> build -> tests -> code review -> security -> evidence -> merge`.

Approved patterns/candidates:

- OpenSpec — spec/proposal/design/tasks.
- Claudex Loop — Claude Code/Codex cross-review.
- Worktrunk — POC for isolated parallel worktrees.
- gstack — selected CEO/engineering/design/review/QA/security/release methods.
- shadcn/improve — evidence-backed findings, self-contained plans, STOP conditions, verification gates.
- Ponytail — minimal implementation gate.
- Dagger — POC for portable build/test/package/release.
- Serena/Graphify/OpenWiki — code intelligence/reference/derived documentation roles; none becomes source-of-truth over Git.

Hard rule: the builder is never the sole inspector of its own change.

## 3. Tool Platform

### Tool SDK

FastMCP is the first POC candidate for typed MCP service creation.

Every registered tool must carry:

- tool_id/version/owner/project;
- read_only and side_effect classification;
- required scopes;
- risk level;
- input/output schema;
- timeout/cost class;
- provenance expectations;
- approval policy.

### Tool Gateway

Evaluate/adapt ContextForge, Archestra and MCP Gateway Registry patterns for:

- MCP/A2A/REST/gRPC routing;
- authn/authz;
- rate limits/retry;
- discovery/catalog;
- OAuth on-behalf-of where applicable;
- audit and OpenTelemetry.

## 4. Action Firewall

Before tool execution:

`proposed action -> deterministic policy -> risk classification -> ALLOW | REQUIRE_APPROVAL | DENY`.

Adopt OpenWorker/Cordum concepts:

- immutable hard floors for irreversible/high-impact actions;
- earned autonomy;
- approval provenance;
- circuit breaker;
- no self-granted privileges;
- unattended runs never bypass hard approvals.

## 5. Execution Cell

Benchmark OpenSandbox vs OpenShell.

Required sandbox contract:

- isolated filesystem;
- no production credentials in workload;
- explicit network egress allowlist;
- resource/time quotas;
- artifact export only through governed channels;
- full execution trace.

## 6. Security Gate

Layered checks:

- skills: NVIDIA SkillSpector;
- MCP: Cisco MCP Scanner;
- model/agent behavior: garak + Scenario/Inspect suites;
- SAST: Semgrep vs OpenGrep benchmark;
- secrets: Gitleaks;
- dependencies/containers: OSV-Scanner/Trivy;
- upstream posture: OpenSSF Scorecard;
- SBOM/provenance: Syft + Cosign/SLSA as appropriate.

## 7. MCP Quality Lab

Use:

- official `modelcontextprotocol/inspector` for protocol/conformance/smoke;
- MCPJam for cross-client/cross-model behavior, OAuth debugging and regression;
- Scenario/Promptfoo for project-specific behavioral tests.

No MCP enters production based only on "it connects".

## 8. Evaluation and telemetry

Instrumentation standard: OpenTelemetry/OpenLLMetry.

Required run fields:

`trace_id, run_id, agent_id, project_id, model, tool, tokens, latency, cost, result, error, security_event, parent_run, approval_provenance`.

Backends are replaceable. Phoenix/Langfuse/Helicone/AgentOps may consume the same telemetry.

## 9. Working Context

Working/execution context is separate from the Second Brain. Preserve:

- objective;
- decisions;
- files;
- errors;
- tests;
- todos;
- hypotheses;
- blockers;
- last valid state.

CocoIndex/QMD/Graphify/OpenWiki may feed selective context; none may promote a claim to canonical knowledge by itself.
