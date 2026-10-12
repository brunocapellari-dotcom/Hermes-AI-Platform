# GO_LIVE_STATUS

Canonical operational status for Hermes go-live work.

| ID | Task | Priority | Status | Dependency | Acceptance | Test | Evidence | Commit | Blocker |
|---|---|---:|---|---|---|---|---|---|---|
| HGL-000 | Zero-cost production baseline | P0 | TESTING | none | zero incremental vendor spend; paid cloud/providers not required | unit + configuration + local deploy | `docs/ZERO_COST_RUNTIME.md`; PR #23 | e16dd204a32caff5c8c78c9c95ec313eee9df220 | local smoke still required |
| HGL-001 | Restore green baseline CI on foundation | P0 | DONE | none | contract CI, manifest CI, foundation CI all green | GitHub Actions | PR #8; PR #1 | 6d890e7a70070b85c8c78c9c95ec313eee9df220 | none |
| HGL-002 | Canonical Request/Task/Workflow/Event/Error contracts | P0 | DONE | HGL-001 | schemas match operational mission and reject invalid states | unit + schema tests | PR #12 | bd5428f8e040e281bcd8a9f1c47d7241301e4b82 | none |
| HGL-003 | Durable request/task/event persistence + migrations | P0 | DONE | HGL-002 | restart-safe state with versioned migrations | migration + integration | PR #12 | bd5428f8e040e281bcd8a9f1c47d7241301e4b82 | none |
| HGL-004 | Event envelope + outbox/event delivery | P0 | REVIEW | HGL-003 | versioned event persisted before delivery; replay safe | integration + failure test | PR #13 | 55e11a28ff495fdfa9378f081d0a4e24ffd47f99 | delivery worker/handoff still required |
| HGL-005 | Retry taxonomy + DLQ + controlled replay | P0 | DOING | HGL-003 | permanent failures land in DLQ after bounded retry | unit + integration | event DLQ/replay in PR #13 | 55e11a28ff495fdfa9378f081d0a4e24ffd47f99 | task execution retry taxonomy not fully wired |
| HGL-006 | Checkpoint/resume + leases/heartbeats/cancellation | P0 | DOING | HGL-003 | interrupted workflow resumes correct stage; dead worker recoverable | integration + failure test | checkpoints PR #12; cancel API PR #22 | 48492ca3b32caff5dcd69de6aae0b3daefd300e0 | leases/heartbeats and executor resume still open |
| HGL-007 | Priority P0-P3 + backpressure/resource controls | P0 | TODO | HGL-003 | P0 outruns P3 backfill without starvation/overload | priority/load test | pending | pending | none |
| HGL-008 | Registry-driven routing + health/fallback | P0 | REVIEW | HGL-002 | no production routing dependency on static default map | unit + integration | PR #22 canonical request path | 48492ca3b32caff5dcd69de6aae0b3daefd300e0 | legacy mission path still has static router |
| HGL-009 | Holding PAUSED/DISCONTINUED/MAINTENANCE admission | P0 | DONE | HGL-008 | prohibited project state prevents new work deterministically | policy integration | PR #22 tests | 48492ca3b32caff5dcd69de6aae0b3daefd300e0 | none |
| HGL-010 | Human action event + approval contract alignment | P0 | TODO | HGL-002 | human gate emits HUMAN_ACTION_REQUIRED with minimal action payload | unit + integration | pending | pending | none |
| HGL-011 | URL/file safety + external input boundary consolidation | P0 | DOING | HGL-002 | SSRF, malicious URL/file and tool-injection tests pass | security tests | loopback URL policy PR #14 | 50e8a85487459b3773b536481775bf797876ba3e | file/upload boundary still open |
| HGL-012 | Holding status/health/cost/failure handoff | P0 | TODO | HGL-004 | Holding receives contracted operational events/API output | integration | pending | pending | none |
| HGL-013 | E2E Research AI -> Hermes -> AgroLog -> Holding | P0 | TODO | HGL-004,HGL-008,HGL-012 | no manual intervention in path | E2E | pending | pending | none |
| HGL-014 | E2E WhatsApp Freight -> Hermes -> AgroLog -> Holding | P0 | TODO | HGL-004,HGL-008,HGL-012 | idempotent freight flow completes | E2E + duplicate replay | pending | pending | none |
| HGL-015 | E2E second domain (Content Factory) | P0 | TODO | HGL-004,HGL-008,HGL-012 | small brief reaches final output/status | E2E | pending | pending | none |
| HGL-016 | Second execution without code changes | P0 | TODO | HGL-013,HGL-014,HGL-015 | all selected flows run again on new inputs | E2E rerun | pending | pending | none |
| HGL-017 | Security regression gate | P0 | TESTING | HGL-011 | auth bypass, privilege, injection, replay, secret leakage blocked | security suite | foundation CI + supply-chain/security checks green | e16dd204a32caff5c8c78c9c95ec313eee9df220 | complete targeted regression matrix still required |
| HGL-018 | Backup + restore drill | P0 | TESTING | HGL-003 | restore reproduces required operational state | restore drill | backup/restore CLI + unit roundtrip PR #23 | e16dd204a32caff5c8c78c9c95ec313eee9df220 | real local drill still required |
| HGL-019 | Reproducible deploy + smoke + rollback | P0 | TESTING | all preceding P0 | same green commit deploys locally/containerized at R$0 incremental vendor spend and can roll back; paid cloud optional | deploy/smoke/rollback | hardened zero-cost compose PR #23 | e16dd204a32caff5c8c78c9c95ec313eee9df220 | local smoke/rollback execution still required |
| HGL-020 | GO-LIVE gate | P0 | TODO | HGL-000..019 | no unmitigated P0 and final question is YES | full gate review | pending | pending | none |

## Scope freeze

Until HGL-020 is DONE, new P2/P3 capabilities are post-go-live backlog. Hermes remains horizontal: Holding governs, Hermes orchestrates, projects execute, and canonical knowledge remains outside Hermes.
