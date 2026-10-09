# Durable execution benchmark

Date: 2026-09-21.

Hermes does not currently have a permanently selected durable execution engine. DBOS, Temporal and Restate are benchmark candidates behind the Hermes mission/durable boundary.

The existing DBOS implementation is a reference candidate, not an architectural commitment.

## Candidate snapshot

| Engine | Current reason to test | Main architectural cost/risk to measure |
|---|---|---|
| DBOS | lightweight Python integration, Postgres-backed workflows/queues, existing Hermes implementation | distributed recovery operations, 2.x -> 3.x migration/version compatibility, Postgres/system-schema coupling |
| Temporal | mature workflow replay, history-based determinism checks, explicit workflow versioning ecosystem, multi-language platform | extra service/control plane, operational complexity and resource footprint |
| Restate | durable services/workflows, exactly-once-per-ID workflow model, virtual objects, signals/promises, Python 1.x and Pydantic AI integration | separate Restate server/runtime model, deployment/operational footprint and migration learning curve |

No qualitative row selects a winner.

## Canonical test scenarios

The executable scenario registry lives in src/hermes/durable_benchmark.py.

Every candidate must run the exact same mission fixture and external side-effect simulator.

### crash_resume

Start a mission, complete at least one side-effect-free step, kill the executor while a later step is running, restart the execution layer and verify recovery from durable state.

Evidence:
- persisted workflow/mission identity;
- completed step not re-executed unnecessarily;
- final mission reaches expected status;
- recovery latency.

### no_duplicate_side_effect

Use a fake external project endpoint that records mutation idempotency keys. Crash the worker after the external mutation is accepted but before local completion acknowledgement.

Pass condition:
- exactly one external side effect;
- replay/recovery does not create a second mutation;
- Hermes mission ends with the original result or a safely reconciled result.

This scenario is a hard gate. A candidate with any duplicate side effect is ineligible.

### parallel_fanout_join

Run a DAG with multiple dependency-independent tasks, verify true parallel execution where supported and deterministic join semantics.

Measure:
- throughput;
- fan-out overhead;
- failure propagation;
- cancellation behavior.

### signal_wait

Suspend a workflow waiting for an external approval/event and resume it later.

Measure:
- worker resources held while waiting;
- persistence/recovery across process restart;
- signal/query semantics;
- timeout/cancellation behavior.

### version_upgrade

Keep an old workflow in flight while deploying a new application version.

Pass condition:
- new workflows use the new version;
- existing workflow can finish or be explicitly migrated according to documented procedure;
- no silent nondeterminism or incompatible history/state access.

DBOS 3.x receives special attention because its 3.0 migration changes persisted workflow input/output storage and has one-way compatibility implications for 2.x rollback.

### queue_backpressure

Create a sustained backlog and verify:
- global/worker concurrency limits;
- rate limiting where available;
- fair progress;
- no starvation of control operations;
- observable queue depth and failures.

### long_idle_wait

Wait for a long external delay without holding an application worker continuously when the engine supports suspension.

### observability

Every engine must expose enough identifiers to correlate:
Hermes mission -> durable workflow -> durable step -> external project/tool call -> failure/recovery.

OpenTelemetry is the canonical telemetry format. An engine-specific UI is supplementary.

### local_reproducibility

The full crash/recovery fixture must run in repeatable local/CI infrastructure without requiring a managed cloud account.

### operator_recovery

Document and execute worker/node failure recovery:
- how abandoned work is detected;
- how another executor claims it;
- how duplicate recovery is prevented;
- how an operator inspects/resumes/cancels failed workflows.

## Metrics

Collect at minimum:

- pass/fail for each required scenario;
- recovery latency;
- duplicate external side effects;
- steady-state task throughput;
- p50/p95 orchestration overhead;
- idle resource use;
- database/storage growth per 1,000 workflow steps;
- minimum infrastructure components;
- operational actions required after worker/node failure;
- migration/versioning complexity;
- observability completeness;
- Python SDK ergonomics and testability.

## Selection gate

An engine is eligible only if all required scenarios pass and duplicate_side_effects == 0.

After eligibility, select using measured Hermes needs, in this order:

1. correctness and recovery;
2. safe version upgrades;
3. operational simplicity;
4. observability;
5. performance;
6. infrastructure cost;
7. developer ergonomics.

Do not pick an engine based on popularity, existing implementation sunk cost or feature-count alone.

## Current repository policy

- DBOS remains installed because the current reference worker uses it.
- Temporal and Restate are not added to core dependencies before the benchmark runner can execute.
- No second production durable engine runs in parallel.
- Hermes MissionStore remains the canonical mission-level state independent of engine choice.
- Engine-specific workflow state remains an implementation detail behind the durable boundary.
