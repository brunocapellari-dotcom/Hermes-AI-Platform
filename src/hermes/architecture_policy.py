from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AdoptionDecision(StrEnum):
    ADOPT = "ADOPT"
    ADOPT_PATTERN = "ADOPT_PATTERN"
    BENCHMARK = "BENCHMARK"
    RESERVE = "RESERVE"
    REJECT = "REJECT"


class ComponentDecision(BaseModel):
    component: str
    responsibility: str
    decision: AdoptionDecision
    canonical_owner: str
    rationale: str
    runtime_dependency: bool = False
    constraints: list[str] = Field(default_factory=list)


PYDANTIC_HARNESS_DECISIONS: tuple[ComponentDecision, ...] = (
    ComponentDecision(
        component="Coder",
        responsibility="coding agent composition",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_AGENT_FACTORY",
        rationale="reuse composition ideas, never unrestricted host shell as a production default",
        constraints=["sandbox required", "least privilege", "repository scope only"],
    ),
    ComponentDecision(
        component="Researcher",
        responsibility="research agent composition",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="RESEARCH_AI",
        rationale="reuse bounded-output and delegated-research patterns; Research AI remains owner",
    ),
    ComponentDecision(
        component="FileSystem",
        responsibility="workspace file access",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_TOOL_GATEWAY",
        rationale="workspace-scoped filesystem access is useful when policy-authorized",
        constraints=["path isolation", "protected files", "audit writes"],
    ),
    ComponentDecision(
        component="Shell",
        responsibility="command execution",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_TOOL_GATEWAY",
        rationale="use bounded shell semantics, not Harness Coder's unrestricted host-shell default",
        constraints=["sandbox", "allowlist", "timeouts", "credential stripping", "approval"],
    ),
    ComponentDecision(
        component="RepoContext",
        responsibility="repository context loading",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_CONTEXT_ROUTER",
        rationale="load repository guidance and structure on demand without becoming long-term memory",
    ),
    ComponentDecision(
        component="Memory",
        responsibility="persistent agent memory",
        decision=AdoptionDecision.REJECT,
        canonical_owner="SECOND_BRAIN",
        rationale="a second canonical memory would duplicate the Second Brain and Hermes operational stores",
        constraints=["ephemeral scratch memory may exist but cannot become canonical knowledge"],
    ),
    ComponentDecision(
        component="Conversation Search",
        responsibility="conversation retrieval",
        decision=AdoptionDecision.RESERVE,
        canonical_owner="HERMES_CONTEXT_ROUTER",
        rationale="use only when stored conversation history exists and retrieval improves context selection",
    ),
    ComponentDecision(
        component="Skills",
        responsibility="skill discovery and loading",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_SKILL_FACTORY",
        rationale="support progressive disclosure/SKILL.md compatibility through Hermes registry and audit",
    ),
    ComponentDecision(
        component="Planning",
        responsibility="task planning",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_TASK_DAG",
        rationale="model-owned planning can propose plans; Hermes Task DAG remains authoritative",
    ),
    ComponentDecision(
        component="SubAgents",
        responsibility="agent delegation",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_AGENT_ROUTER",
        rationale="bounded delegation is useful when agents are registry-backed and least-privilege",
    ),
    ComponentDecision(
        component="Dynamic Workflow",
        responsibility="model-orchestrated fanout/chain/vote",
        decision=AdoptionDecision.BENCHMARK,
        canonical_owner="HERMES_TASK_DAG",
        rationale="evaluate bounded dynamic composition without allowing it to replace durable mission state",
        constraints=["hard agent-call budget", "durable checkpoints", "policy per child task"],
    ),
    ComponentDecision(
        component="Advisor",
        responsibility="stronger-model consultation",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_REVIEW_PANEL",
        rationale="maps cleanly to critic/judge/auditor escalation through Model Router",
    ),
    ComponentDecision(
        component="Tool Search",
        responsibility="on-demand tool discovery",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_TOOL_REGISTRY",
        rationale="lazy tool loading reduces prompt size while registry/policy retain authority",
    ),
    ComponentDecision(
        component="Compaction",
        responsibility="context compaction",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_CONTEXT_ROUTER",
        rationale="context reduction is useful but summaries are not canonical memory",
    ),
    ComponentDecision(
        component="Tool Output Limits",
        responsibility="tool-result bounding",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_TOOL_GATEWAY",
        rationale="bound/truncate/spill large tool results before model context ingestion",
    ),
    ComponentDecision(
        component="Playwright Browser",
        responsibility="deterministic browser automation",
        decision=AdoptionDecision.RESERVE,
        canonical_owner="RESEARCH_AI",
        rationale="use for browser-required research/testing; not a general Hermes runtime dependency",
    ),
    ComponentDecision(
        component="Browser Use",
        responsibility="autonomous browser execution",
        decision=AdoptionDecision.RESERVE,
        canonical_owner="RESEARCH_AI",
        rationale="higher autonomy than deterministic browser control requires stronger sandbox and approval",
    ),
    ComponentDecision(
        component="Guardrails",
        responsibility="input/tool/output validation",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_SECURITY",
        rationale="select useful guards behind Hermes policy/privacy boundaries rather than delegate authority",
    ),
    ComponentDecision(
        component="Prompt Injection Defender",
        responsibility="indirect prompt-injection detection",
        decision=AdoptionDecision.BENCHMARK,
        canonical_owner="HERMES_SECURITY",
        rationale="use as an additional signal only; authorization never depends on a classifier alone",
    ),
    ComponentDecision(
        component="Spend Limits",
        responsibility="token/cost budgets",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_BUDGET_GUARD",
        rationale="cross-window budget ideas complement the canonical Hermes usage ledger",
    ),
    ComponentDecision(
        component="Tool Approval",
        responsibility="human approval",
        decision=AdoptionDecision.ADOPT_PATTERN,
        canonical_owner="HERMES_POLICY_ENGINE",
        rationale="deferred approval maps to existing owner-approval boundaries",
    ),
    ComponentDecision(
        component="Trajectory Judge",
        responsibility="long-run trajectory review",
        decision=AdoptionDecision.BENCHMARK,
        canonical_owner="HERMES_EVALUATION",
        rationale="valuable for long missions if cost and false-positive rate justify mid-run steering",
    ),
    ComponentDecision(
        component="Capability Creation",
        responsibility="self-extension",
        decision=AdoptionDecision.BENCHMARK,
        canonical_owner="HERMES_AGENT_SKILL_FACTORY",
        rationale="generated capabilities must pass sandbox, tests, benchmark, security and independent audit",
        constraints=["no direct production registration", "no self-granted permissions"],
    ),
    ComponentDecision(
        component="Step Persistence",
        responsibility="run checkpoint persistence",
        decision=AdoptionDecision.REJECT,
        canonical_owner="HERMES_DURABLE_ENGINE",
        rationale="a second step store would duplicate the selected durable execution engine",
        constraints=["may be used only in isolated local benchmark fixtures"],
    ),
    ComponentDecision(
        component="OpenTelemetry instrumentation",
        responsibility="distributed telemetry",
        decision=AdoptionDecision.ADOPT,
        canonical_owner="HERMES_OTEL",
        rationale="OpenTelemetry remains the vendor-neutral telemetry standard",
        runtime_dependency=True,
    ),
)


def decision_for(component: str) -> ComponentDecision:
    normalized = component.casefold()
    for decision in PYDANTIC_HARNESS_DECISIONS:
        if decision.component.casefold() == normalized:
            return decision
    raise KeyError(component)


def validate_component_matrix(
    decisions: tuple[ComponentDecision, ...] = PYDANTIC_HARNESS_DECISIONS,
) -> None:
    names: set[str] = set()
    for decision in decisions:
        key = decision.component.casefold()
        if key in names:
            raise ValueError(f"duplicate component decision: {decision.component}")
        names.add(key)
        if decision.runtime_dependency and decision.decision not in {
            AdoptionDecision.ADOPT,
            AdoptionDecision.ADOPT_PATTERN,
        }:
            raise ValueError(
                f"runtime dependency cannot be {decision.decision}: {decision.component}"
            )
        if not decision.canonical_owner.startswith(("HERMES_", "SECOND_BRAIN", "RESEARCH_AI")):
            raise ValueError(f"non-canonical owner: {decision.canonical_owner}")


PLATFORM_COMPONENT_DECISIONS: tuple[ComponentDecision, ...] = (
    ComponentDecision(
        component="DBOS",
        responsibility="durable execution",
        decision=AdoptionDecision.BENCHMARK,
        canonical_owner="HERMES_DURABLE_ENGINE",
        rationale="current reference implementation; must compete under the same crash/idempotency/versioning benchmark",
    ),
    ComponentDecision(
        component="Temporal",
        responsibility="durable execution",
        decision=AdoptionDecision.BENCHMARK,
        canonical_owner="HERMES_DURABLE_ENGINE",
        rationale="strong replay/versioning ecosystem; additional control-plane cost must be measured",
    ),
    ComponentDecision(
        component="Restate",
        responsibility="durable execution",
        decision=AdoptionDecision.BENCHMARK,
        canonical_owner="HERMES_DURABLE_ENGINE",
        rationale="durable services/workflows and Pydantic AI integration merit an equal benchmark",
    ),
    ComponentDecision(
        component="ToolHive",
        responsibility="MCP runtime/registry/gateway",
        decision=AdoptionDecision.BENCHMARK,
        canonical_owner="HERMES_MCP_GATEWAY",
        rationale="evaluate isolation, signed artifacts, registry and virtual MCP patterns without duplicating Hermes control plane",
        constraints=["security advisory regression suite", "deny-by-default egress", "no parallel canonical gateway"],
    ),
    ComponentDecision(
        component="IBM ContextForge",
        responsibility="MCP federation/A2A/plugin gateway",
        decision=AdoptionDecision.BENCHMARK,
        canonical_owner="HERMES_MCP_GATEWAY",
        rationale="benchmark federation, A2A and plugin hooks as complementary patterns only",
        constraints=["no second canonical registry", "no second policy authority"],
    ),
    ComponentDecision(
        component="Arize Phoenix",
        responsibility="AI observability UI and trace analysis",
        decision=AdoptionDecision.ADOPT,
        canonical_owner="HERMES_OTEL",
        rationale="preferred optional OpenTelemetry analysis backend; OTel and Hermes ledger remain canonical",
    ),
    ComponentDecision(
        component="Promptfoo",
        responsibility="LLM regression and red-team",
        decision=AdoptionDecision.ADOPT,
        canonical_owner="HERMES_EVALUATION",
        rationale="primary declarative regression and adversarial suite once live endpoints exist",
    ),
    ComponentDecision(
        component="DeepEval",
        responsibility="Python-native LLM component tests",
        decision=AdoptionDecision.RESERVE,
        canonical_owner="HERMES_EVALUATION",
        rationale="use only for Python-specific assertions/metrics that Promptfoo and deterministic tests do not cover",
    ),
    ComponentDecision(
        component="Ragas",
        responsibility="RAG retrieval/generation evaluation",
        decision=AdoptionDecision.ADOPT,
        canonical_owner="HERMES_EVALUATION",
        rationale="specialized RAG evaluation for Second Brain/retrieval pipelines, not general agent regression",
    ),
)


def validate_all_component_matrices() -> None:
    validate_component_matrix(PYDANTIC_HARNESS_DECISIONS)
    validate_component_matrix(PLATFORM_COMPONENT_DECISIONS)
