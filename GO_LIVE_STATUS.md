# GO_LIVE_STATUS

Canonical operational status for Hermes go-live work.

| ID | Task | Priority | Status | Dependency | Acceptance | Test | Evidence | Commit | Blocker |
|---|---|---:|---|---|---|---|---|---|---|
| HGL-000 | Zero-cost production baseline | P0 | TESTING | none | zero incremental vendor spend; paid cloud/providers not required | unit + configuration + local deploy | `docs/ZERO_COST_RUNTIME.md` | pending | CI validation pending |
| HGL-001 | Restore green baseline CI on foundation | P0 | TESTING | none | contract CI, manifest CI, foundation CI all green | GitHub Actions | PR #8 | 3d9eabce62e313cac963874846706eb539c37d02 | foundation CI pending |
| HGL-002 | Canonical Request/Task/Workflow/Event/Error contracts | P0 | READY | HGL-001 | schemas match operational mission and reject invalid states | unit + schema tests | pending | pending | none |
| HGL-003 | Durable request/task/event persistence + migrations | P0 | TODO | HGL-002 | restart-safe state with versioned migrations | migration + integration | pending | pending | none |
| HGL-004 | Event envelope + outbox/event delivery | P0 | TODO | HGL-003 | versioned event persisted before delivery; replay safe | integration + failure test | pending | pending | none |
| HGL-005 | Retry taxonomy + DLQ + controlled replay | P0 | TODO | HGL-003 | permanent failures land in DLQ after bounded retry | unit + integration | pending | pending | none |
| HGL-006 | Checkpoint/resume + leases/heartbeats/cancellation | P0 | TODO | HGL-003 | interrupted workflow resumes correct stage; dead worker recoverable | integration + failure test | pending | pending | none |
| HGL-007 | Priority P0-P3 + backpressure/resource controls | P0 | TODO | HGL-003 | P0 outruns P3 backfill without starvation/overload | priority/load test | pending | pending | none |
| HGL-008 | Registry-driven routing + health/fallback | P0 | TODO | HGL-002 | no production routing dependency on static default map | unit + integration | pending | pending | none |
| HGL-009 | Holding PAUSED/DISCONTINUED/MAINTENANCE admission | P0 | TODO | HGL-008 | prohibited project state prevents new work deterministically | policy integration | pending | pending | none |
| HGL-010 | Human action event + approval contract alignment | P0 | TODO | HGL-002 | human gate emits HUMAN_ACTION_REQUIRED with minimal action payload | unit + integration | pending | pending | none |
| HGL-011 | URL/file safety + external input boundary consolidation | P0 | TODO | HGL-002 | SSRF, malicious URL/file and tool-injection tests pass | security tests | pending | pending | none |
| HGL-012 | Holding status/health/cost/failure handoff | P0 | TODO | HGL-004 | Holding receives contracted operational events/API output | integration | pending | pending | none |
| HGL-013 | E2E Research AI -> Hermes -> AgroLog -> Holding | P0 | TODO | HGL-004,HGL-008,HGL-012 | no manual intervention in path | E2E | pending | pending | none |
| HGL-014 | E2E WhatsApp Freight -> Hermes -> AgroLog -> Holding | P0 | TODO | HGL-004,HGL-008,HGL-012 | idempotent freight flow completes | E2E + duplicate replay | pending | pending | none |
| HGL-015 | E2E second domain (Content Factory) | P0 | TODO | HGL-004,HGL-008,HGL-012 | small brief reaches final output/status | E2E | pending | pending | none |
| HGL-016 | Second execution without code changes | P0 | TODO | HGL-013,HGL-014,HGL-015 | all selected flows run again on new inputs | E2E rerun | pending | pending | none |
| HGL-017 | Security regression gate | P0 | TODO | HGL-011 | auth bypass, privilege, injection, replay, secret leakage blocked | security suite | pending | pending | none |
| HGL-018 | Backup + restore drill | P0 | TODO | HGL-003 | restore reproduces required operational state | restore drill | pending | pending | none |
| HGL-019 | Reproducible deploy + smoke + rollback | P0 | TODO | all preceding P0 | same green commit deploys locally/containerized at R$0 incremental vendor spend and can roll back; paid cloud optional | deploy/smoke/rollback | pending | pending | none |
| HGL-020 | GO-LIVE gate | P0 | TODO | HGL-000..019 | no unmitigated P0 and final question is YES | full gate review | pending | pending | none |

## Scope freeze

Until HGL-020 is DONE, new P2/P3 capabilities are post-go-live backlog. Hermes remains horizontal: Holding governs, Hermes orchestrates, projects execute, and canonical knowledge remains outside Hermes.
