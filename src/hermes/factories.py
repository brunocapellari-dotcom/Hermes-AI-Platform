from __future__ import annotations

from pydantic import BaseModel, Field

from hermes.domain import AgentSpec, PermissionSet, RiskLevel, SkillSpec


class AgentNeedDetector:
    def decide(
        self, *, recurring: bool, own_state: bool, own_tools: bool, independent_lifecycle: bool
    ) -> str:
        score = sum((recurring, own_state, own_tools, independent_lifecycle))
        return "agent" if score >= 3 else "skill"


class AgentFactory:
    def specification(
        self, *, name: str, project: str, mission: str, read_scopes: list[str]
    ) -> AgentSpec:
        return AgentSpec(
            name=name,
            project=project,
            mission=mission,
            permissions=PermissionSet(read_scopes=read_scopes),
            autonomy_level=0,
            risk=RiskLevel.LOW,
            status="sandbox",
        )


class SkillFactory:
    def specification(
        self,
        *,
        purpose: str,
        inputs: list[str],
        outputs: list[str],
        procedure: list[str],
        validation: list[str],
    ) -> SkillSpec:
        if not validation:
            raise ValueError("skills require explicit validation")
        return SkillSpec(
            purpose=purpose,
            inputs=inputs,
            outputs=outputs,
            procedure=procedure,
            validation=validation,
        )


class AgentAuditResult(BaseModel):
    passed: bool
    promotable: bool
    findings: list[str] = Field(default_factory=list)


class AgentAuditor:
    def audit(
        self,
        spec: AgentSpec,
        *,
        tests_passed: bool,
        benchmark_passed: bool,
        independent_review_passed: bool,
        external_action_approved: bool = False,
    ) -> AgentAuditResult:
        findings: list[str] = []
        if not spec.project or not spec.mission:
            findings.append("agent scope is incomplete")
        if spec.permissions.money or spec.permissions.production_admin:
            findings.append("agent cannot receive money or production-admin authority by factory promotion")
        if spec.permissions.external_actions and not external_action_approved:
            findings.append("external action permission lacks explicit owner approval")
        if not tests_passed:
            findings.append("tests failed or missing")
        if not benchmark_passed:
            findings.append("benchmark failed or missing")
        if not independent_review_passed:
            findings.append("independent review failed or missing")
        passed = not findings
        return AgentAuditResult(passed=passed, promotable=passed and spec.status == "sandbox", findings=findings)

    def promote(self, spec: AgentSpec, audit: AgentAuditResult) -> AgentSpec:
        if not audit.promotable:
            raise ValueError("agent cannot be promoted without a passing independent audit")
        spec.status = "active"
        return spec


class SkillAuditResult(BaseModel):
    passed: bool
    promotable: bool
    findings: list[str] = Field(default_factory=list)


class SkillAuditor:
    def audit(
        self,
        spec: SkillSpec,
        *,
        tests_passed: bool,
        benchmark_passed: bool,
        independent_review_passed: bool,
    ) -> SkillAuditResult:
        findings: list[str] = []
        if not spec.purpose or not spec.procedure:
            findings.append("skill purpose/procedure is incomplete")
        if not spec.validation:
            findings.append("skill has no explicit validation")
        if not tests_passed:
            findings.append("tests failed or missing")
        if not benchmark_passed:
            findings.append("benchmark failed or missing")
        if not independent_review_passed:
            findings.append("independent review failed or missing")
        passed = not findings
        return SkillAuditResult(passed=passed, promotable=passed, findings=findings)

    def promote(self, spec: SkillSpec, audit: SkillAuditResult) -> SkillSpec:
        if not audit.promotable:
            raise ValueError("skill cannot be promoted without a passing independent audit")
        return spec
