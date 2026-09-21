# Gap Analysis

Status is evidence-based: EXISTE, PARCIAL, FALTA, QUEBRADO, DUPLICADO, OBSOLETO. `EXISTE` means a tested repository implementation exists; it never means live production operation.

| gap_id | area | status | priority | current evidence | remaining acceptance evidence |
|---|---|---|---|---|---|
| H-001 | repository/API foundation | EXISTE | P0 | FastAPI + CI + container + persistence | complete integrated gate on final candidate |
| H-002 | intent/goal interpretation | PARCIAL | P0 | hybrid model/fallback engine | benchmark Portuguese intents with live models |
| H-003 | task DAG planner | PARCIAL | P0 | deterministic dependency graph | complex mission golden set + parallel graph/live cases |
| H-004 | project router/contracts | PARCIAL | P0 | capability routing + canonical contracts for ecosystem | live capability discovery and contract tests for every project |
| H-005 | model gateway | PARCIAL | P0 | OpenAI-compatible gateway contract | live LiteLLM multi-provider fallback |
| H-006 | model router/registry | PARCIAL | P0 | persistent registry + ranking/fallback | real benchmark/cost/latency telemetry |
| H-007 | local inference | PARCIAL | P0 | hardware discovery; vLLM/llama.cpp primary candidates; SGLang benchmark | actual hardware/model E2E benchmark |
| H-008 | Second Brain interpreter | PARCIAL | P0 | temporal Evidence contract/client | live validated/conflicting/superseded cases |
| H-009 | Research handoff | PARCIAL | P0 | automatic gap-triggered client | live Research Package roundtrip |
| H-010 | authorization/tool gateway | PARCIAL | P0 | fail-closed local policy + OPA/OpenFGA clients + Tool Gateway + lazy tool search/output bounds | live identities/policies/relationship tuples + adversarial authorization tests |
| H-011 | durable missions | PARCIAL | P0 | SQL checkpoints + DBOS reference dispatcher/worker + neutral DBOS/Temporal/Restate benchmark contract | execute all canonical benchmark scenarios against every candidate before selecting one engine |
| H-012 | Agent Factory/Auditor | EXISTE | P1 | least-privilege spec + test/benchmark/independent-review promotion gate | live sandbox agent benchmark before any operational promotion |
| H-013 | Skill Factory | PARCIAL | P1 | versionable validated spec | persisted promotion/rollback E2E |
| H-014 | Cross-project intelligence | PARCIAL | P1 | relation rules | evidence-driven cross-project benchmark |
| H-015 | observability/FinOps | PARCIAL | P0 | persisted usage ledger + Prometheus + Hermes/DBOS OpenTelemetry instrumentation | OTel E2E export + Phoenix trace/eval backend + BigQuery analytical export |
| H-016 | Control Center | PARCIAL | P2 | backend world-state/daily-intelligence/project-contract snapshot | operator UI only if it adds value without duplicating Holding PMO |
| H-017 | Security Test Lab | PARCIAL | P0 | injection/authority tests + dependency audit + fail-closed auth + MCP workload permission/provenance policy | live Promptfoo/Garak + ToolHive advisory regressions + adversarial MCP-egress-gateway suite |
| H-018 | GCP production readiness | PARCIAL | P0 | VPC/private Cloud SQL/Secret IAM/Direct VPC Terraform + Alembic migration path | plan/apply + secrets + migration + smoke + restore/rollback drill |
| H-019 | Holding integration | PARCIAL | P0 | read adapter and boundary contract | authenticated live read contract |
| H-020 | all project adapters | PARCIAL | P0 | canonical 12-project contract/validator + health/status/capabilities/query/search/alerts contract + execute/idempotency validation | every project passes live contract discovery and authorized execute/idempotency tests where applicable |
| H-021 | World State | EXISTE | P1 | registry/mission/audit/usage snapshot | keep regression coverage in integrated gate |
| H-022 | Context/privacy router | PARCIAL | P0 | tenant/health/credential/project isolation | production identity and external policy tests |
| H-023 | Scenario/Hypothesis engines | EXISTE | P1 | explicit assumptions/epistemic labels | keep deterministic regression tests |
| H-024 | controlled self-improvement | PARCIAL | P1 | persisted server-authoritative staged gates + rollback state machine | measured A/B + independent auditor live E2E |
| H-025 | Evaluation/Critic/Judge/Auditor | EXISTE | P1 | deterministic evaluation and independent review panel | live model judge may supplement but never replace deterministic gates |
| H-026 | Failure Recovery Engine | EXISTE | P1 | explicit failure classes/retry/fallback/human policies | integrate measured live failure telemetry |
| H-027 | proactive intelligence | EXISTE | P1 | read-only Daily Intelligence from World State | recurring delivery only after live deployment and owner-authorized scheduling |
| H-028 | multimodal adapters | PARCIAL | P1 | OpenAI-compatible embeddings/vision/STT/TTS/rerank adapters | configure and benchmark real models/providers |
| H-029 | database migrations | EXISTE | P0 | Alembic versioned initial schema + CI empty-db upgrade gate | execute controlled migration against Cloud SQL staging/production |

| H-030 | Pydantic AI Harness capability audit | EXISTE | P1 | executable component matrix covers Coder/Researcher/filesystem/shell/context/memory/planning/subagents/guardrails/budgets/approval/judging/self-extension/durability/OTel | benchmark only the components marked BENCHMARK before any direct dependency promotion |
| H-031 | MCP runtime/federation benchmark | PARCIAL | P1 | ToolHive/ContextForge architecture decisions + native MCP permission/provenance policy | ToolHive isolation/security benchmark and ContextForge federation/A2A/plugin benchmark against Hermes gateway |
| H-032 | evaluation framework routing | EXISTE | P1 | executable single-owner strategy: Hermes deterministic, Promptfoo regression/red-team, Ragas RAG, DeepEval optional Python-specific | live endpoint/RAG suites with objective thresholds |
| H-033 | context efficiency controls | EXISTE | P1 | native Tool Search + Tool Output Limits behind Hermes Tool Gateway | live long-context benchmark; add compaction only if measured token/quality gain justifies it |

No row may become production-operational without its acceptance evidence. Repository implementation and live operational evidence are deliberately separate so the project cannot self-report completion from code existence alone.
