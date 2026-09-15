from __future__ import annotations

from hermes.domain import AgentSpec, PermissionSet, RiskLevel, SkillSpec


class AgentNeedDetector:
    def decide(self, *, recurring: bool, own_state: bool, own_tools: bool, independent_lifecycle: bool) -> str:
        score = sum((recurring, own_state, own_tools, independent_lifecycle))
        return "agent" if score >= 3 else "skill"


class AgentFactory:
    def specification(self, *, name: str, project: str, mission: str, read_scopes: list[str]) -> AgentSpec:
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
