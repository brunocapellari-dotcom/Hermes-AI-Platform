# Full-system acceptance gate

Hermes is not operational merely because code exists.

The final gate must run the entire enabled surface in one release candidate:

1. Owner -> Hermes -> correct project routing.
2. Hermes -> Second Brain -> temporal validated/superseded/conflicting interpretation.
3. Knowledge gap -> Research AI -> Research Package -> Second Brain -> mission resume.
4. Model Router -> external model; forced failure -> fallback; breaker opens; local fallback works.
5. Agent need -> Agent/Skill decision -> least privilege -> sandbox -> tests -> benchmark -> auditor -> registry.
6. Untrusted prompt injection -> no privilege escalation.
7. Long mission -> process interruption -> persisted checkpoint -> resume without duplicate side effects.
8. Cross-project signal -> justified beneficiary recommendation.
9. Observability correlates mission, model, tool, latency, token/cost and error.
10. GCP deploy -> smoke -> backup/restore drill -> rollback.
11. Golden Tasks all pass in Portuguese.

CI tests the repository-contained surface on every change. Live external integrations remain BLOCKED, not PASSED, until credentials/endpoints and real services are available.
