# Full-system acceptance gate

Hermes is not operational merely because code exists.

The final gate must run the entire enabled surface in one release candidate. Repository-only checks and live integration checks are both mandatory where applicable.

## Core product acceptance

1. Owner -> Hermes -> correct project routing.
2. Hermes -> Second Brain -> temporal validated/superseded/conflicting interpretation.
3. Knowledge gap -> Research AI -> Research Package -> Second Brain -> mission resume.
4. Model Router -> external model; forced failure -> fallback; breaker opens; local fallback works.
5. Agent need -> Agent/Skill decision -> least privilege -> sandbox -> tests -> benchmark -> auditor -> registry.
6. Duplicate agent/skill proposal -> promotion is rejected or deliberately replaces an existing version through governed lifecycle.
7. Untrusted prompt injection -> no privilege escalation.
8. Cross-project signal -> justified beneficiary recommendation.
9. Golden Tasks all pass in Portuguese.

## Context and capability acceptance

10. Tool Search returns only relevant registered tools and does not expand authorization.
11. Tool Output Limits bound oversized results without changing source-of-truth artifacts.
12. Context compaction, if later enabled, preserves source references and remains derived state.
13. Pydantic AI Harness capability adoption matches the executable architecture matrix; Harness Memory and Step Persistence never become canonical stores.
14. Any generated capability enters only through sandbox -> deterministic tests -> benchmark -> security/adversarial tests -> independent audit -> registry.

## Durable execution acceptance

15. DBOS, Temporal and Restate are measured against the exact same canonical fixture before one engine is permanently selected.
16. Every eligible engine passes all scenarios in src/hermes/durable_benchmark.py:
    - crash/resume;
    - no duplicate external side effect;
    - parallel fan-out/join;
    - signal/wait;
    - version upgrade;
    - queue/backpressure;
    - long idle wait;
    - OpenTelemetry correlation;
    - local reproducibility;
    - operator recovery.
17. The no-duplicate-side-effect scenario has exactly zero duplicate mutations.
18. Old in-flight workflows survive or follow an explicit documented migration path after application upgrade.
19. The selected engine is the only canonical production durable runtime; no parallel durable state store is allowed.

## MCP acceptance

20. Hermes MCP Gateway remains the canonical admission boundary.
21. Native MCP controls pass the Hermes security scenarios.
22. ToolHive must pass all ToolHive scenarios in src/hermes/mcp_benchmark.py before runtime promotion, including authorization bypass, SSRF, host egress, CORS, artifact injection, encoding/filter bypass and provenance.
23. ContextForge must pass federation conflict, A2A authority propagation, plugin isolation and header/identity boundary scenarios before any complementary deployment.
24. MCP workload permissions are deny-by-default, non-privileged and explicit about egress.
25. Pinned MCP workload artifacts require verifiable provenance when policy requires it.

## Evaluation acceptance

26. Deterministic pytest/security/policy tests remain mandatory and cannot be replaced by model judges.
27. Promptfoo runs live endpoint regression against Hermes /v1/chat and the approved red-team suite.
28. Ragas runs only against live Second Brain/RAG flows and measures retrieval/context/faithfulness dimensions appropriate to those flows.
29. DeepEval is added only when a Python-native metric/test closes a documented gap not already covered.
30. Trajectory Judge, if promoted, demonstrates measurable long-mission quality benefit at acceptable latency/cost and never overrides deterministic policy failures.

## Observability and FinOps acceptance

31. OpenTelemetry correlates Hermes mission -> durable workflow -> durable step -> model/tool/project call -> failure/recovery.
32. Phoenix consumes OpenTelemetry traces as the preferred optional AI-observability backend and can be removed without changing Hermes operational correctness.
33. Phoenix is not mission state, authorization state, registry state or FinOps source of truth.
34. PostgreSQL audit/usage records reconcile with exported telemetry for sampled test missions.
35. BigQuery, when enabled, remains analytical only.

## Production/GCP acceptance

36. Repository CI is fully green on the exact release commit: lint, strict typing, security scan, dependency audit, migration, coverage >=90%, policy validation, supply-chain scans, container build and Terraform validation.
37. GCP deploy uses the exact green immutable artifact.
38. Cloud SQL IAM authentication, migrations, runtime grants and private networking pass.
39. OPA/OpenFGA identities, policies and relationship tuples pass live positive and negative authorization tests.
40. Every canonical project passes its declared adapter contract and authorized execute/idempotency tests where applicable.
41. Live model/provider fallback, privacy, MCP adversarial and durable recovery tests pass.
42. Backup restore and runtime/schema rollback procedures are exercised.

CI tests the repository-contained surface on every change. Live external integrations remain BLOCKED, not PASSED, until credentials/endpoints and real services are available. A documentation claim cannot override failing or missing evidence.
