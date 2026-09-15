# Gap Analysis

Status is evidence-based: EXISTE, PARCIAL, FALTA, QUEBRADO, DUPLICADO, OBSOLETO.

| gap_id | area | status | priority | current evidence | acceptance test |
|---|---|---|---|---|---|
| H-001 | repository/API foundation | EXISTE | P0 | FastAPI + CI + container + persistence | integrated CI green |
| H-002 | intent/goal interpretation | PARCIAL | P0 | hybrid model/fallback engine | benchmark Portuguese intents with live models |
| H-003 | task DAG planner | PARCIAL | P0 | deterministic dependency graph | complex mission golden set + parallel graph cases |
| H-004 | project router | PARCIAL | P0 | capability registry | live project capability discovery |
| H-005 | model gateway | PARCIAL | P0 | OpenAI-compatible adapter | live LiteLLM multi-provider fallback |
| H-006 | model router/registry | PARCIAL | P0 | persistent registry + scored ranking/fallback | project benchmarks + real cost/latency telemetry |
| H-007 | local inference | PARCIAL | P0 | hardware discovery + runtime recommendation | real local model E2E |
| H-008 | Second Brain interpreter | PARCIAL | P0 | temporal Evidence contract/client | live validated/conflicting/superseded cases |
| H-009 | Research handoff | PARCIAL | P0 | automatic gap-triggered client | live Research Package roundtrip |
| H-010 | Tool Gateway/policy | PARCIAL | P0 | fail-closed policy + tool gate | OPA/OpenFGA identity integration |
| H-011 | durable missions | PARCIAL | P0 | SQL checkpoints + DBOS durable dispatcher | worker crash/resume + no-duplicate external side effect |
| H-012 | Agent Factory | PARCIAL | P1 | least-privilege specs | sandbox->benchmark->audit->registry E2E |
| H-013 | Skill Factory | PARCIAL | P1 | versionable validated spec | promotion/rollback E2E |
| H-014 | Cross-project intelligence | PARCIAL | P1 | relation rules | evidence-driven relation benchmark |
| H-015 | observability/FinOps | PARCIAL | P0 | persisted usage ledger + Prometheus | OTel end-to-end trace + BigQuery export |
| H-016 | control center | FALTA | P2 | API only | operator UI acceptance suite |
| H-017 | Security Test Lab | PARCIAL | P0 | injection/authority tests + dependency audit | OPA/OpenFGA + egress + adversarial gateway suite |
| H-018 | GCP production | PARCIAL | P0 | VPC/private Cloud SQL/Secret IAM/Direct VPC Terraform | plan/apply + smoke + restore drill |
| H-019 | Holding integration | PARCIAL | P0 | canonical API known, read adapter present | authenticated live read contract |
| H-020 | all project adapters | FALTA | P0 | adapter contract defined | each project health/capabilities/query/execute contract |
| H-021 | World State | EXISTE | P1 | generated registry/mission/audit/usage snapshot | integrated persistence tests |
| H-022 | Context/privacy router | PARCIAL | P0 | tenant/health/credential/project isolation rules | policy-backed production identity tests |
| H-023 | Scenario/Hypothesis engines | EXISTE | P1 | explicit assumptions/epistemic hypothesis labels | deterministic tests |
| H-024 | controlled self-improvement | PARCIAL | P1 | staged gates and rollback state machine | persisted A/B + independent auditor E2E |

No row may become COMPLETED/operational without its acceptance evidence. `EXISTE` means a tested implementation exists in the repository; it does not mean the full Hermes platform is production-operational.
