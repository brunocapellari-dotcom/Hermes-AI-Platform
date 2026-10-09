# Development Executors Policy

GitHub is the canonical source of implementation truth for Hermes. Replit and Claude Code are future execution environments, not independent copies of the project.

## Release gate before external executors

Replit or Claude Code may only be enabled after the integrated repository release candidate is green on the complete gate and all repository-only P0 work is closed with evidence.

## Mandatory workflow after enablement

1. Start from the exact GitHub commit/branch.
2. Work only through branches/commits that return to GitHub.
3. No private state, code, configuration or schema may exist only in Replit or Claude Code.
4. No executor may bypass GitHub CI, authorization rules, migration discipline or human approval boundaries.
5. Generated changes are proposals until the complete repository gate passes again.
6. Secrets remain in an authorized secret store and are never committed or copied into prompts/logs unnecessarily.
7. Claude Code and Replit may implement and test; neither becomes the PMO, source of truth, knowledge authority or governance layer.
8. If two executors produce overlapping solutions, only one canonical implementation is retained after benchmark/review; duplicated stacks are rejected.

## Responsibility boundaries

- GitHub: source, history, review and release evidence.
- Hermes: AI orchestration, routing, policy-aware execution and intelligence.
- Holding: governance, PMO, prioritization, financial/resource control.
- Second Brain: canonical knowledge and provenance.
- Research AI: discovery, verification and source packages.
- Replit / Claude Code: subordinate development executors after the gate above.
