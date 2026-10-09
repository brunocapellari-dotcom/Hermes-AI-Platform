# Development policy

GitHub is canonical. Replit and Claude Code may be used later as execution environments/engineering assistants, but they must work against this repository and branches/PRs; neither becomes a source of truth.

Before external development is enabled:

- CI must be green on main.
- repository visibility and access policy must be intentional;
- branch/review policy must be defined;
- secrets must live outside the repository;
- tool/agent authority must remain bounded by Hermes/Holding policy;
- generated code must pass the same quality/security/E2E gates.

Google Cloud deployment is prepared as IaC under `infra/gcp`. No manual cloud configuration is canonical if it is not represented or documented here.
