# Gap Analysis

Status is evidence-based: EXISTE, PARCIAL, FALTA, QUEBRADO, DUPLICADO, OBSOLETO.

| gap_id | area | status | priority | current evidence | acceptance test |
|---|---|---|---|---|---|
| H-001 | repository/API foundation | EXISTE | P0 | FastAPI + CI + container + persistence | CI green |
| H-002 | intent/goal interpretation | PARCIAL | P0 | hybrid model/fallback engine | benchmark Portuguese intents |
| H-003 | task DAG planner | PARCIAL | P0 | deterministic dependency graph | complex mission golden set |
| H-004 | project router | PARCIAL | P0 | capability registry | live project capability discovery |
| H-005 | model gateway | PARCIAL | P0 | OpenAI-compatible adapter | live LiteLLM multi-provider fallback |
| H-006 | model router/registry | PARCIAL | P0 | evidence-scored router | project benchmarks + cost/latency telemetry |
| H-007 | local inference | PARCIAL | P0 | hardware discovery + runtime recommendation | real local model E2E |
| H-008 | Second Brain interpreter | PARCIAL | P0 | temporal Evidence contract/client | live validated/conflicting/superseded cases |
| H-009 | Research handoff | PARCIAL | P0 | automatic gap-triggered client | live Research Package roundtrip |
| H-010 | Tool Gateway/policy | PARCIAL | P0 | fail-closed policy + tool gate | OPA/OpenFGA identity integration |
| H-011 | durable missions | PARCIAL | P0 | SQL mission/checkpoint persistence | process crash/resume with durable runtime |
| H-012 | Agent Factory | PARCIAL | P1 | least-privilege specs | sandbox->benchmark->audit->registry E2E |
| H-013 | Skill Factory | PARCIAL | P1 | versionable validated spec | promotion/rollback E2E |
| H-014 | Cross-project intelligence | PARCIAL | P1 | relation rules | evidence-driven relation benchmark |
| H-015 | observability/FinOps | FALTA | P0 | telemetry schema target only | trace+token+cost+tool correlation |
| H-016 | control center | FALTA | P2 | API only | operator UI acceptance suite |
| H-017 | Security Test Lab | PARCIAL | P0 | injection/authority tests | adversarial suite + identity + egress tests |
| H-018 | GCP production | PARCIAL | P0 | Terraform topology | plan/apply + smoke + restore drill |
| H-019 | Holding integration | PARCIAL | P0 | canonical API known, read adapter present | authenticated live read contract |
| H-020 | all project adapters | FALTA | P0 | contract defined | each project health/capabilities/query/execute contract |

No row may become COMPLETED/operational without its acceptance evidence.
