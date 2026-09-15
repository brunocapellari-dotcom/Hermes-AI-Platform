from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class EpistemicType(StrEnum):
    FACT = "FATO"
    OBSERVATION = "OBSERVAÇÃO"
    INFERENCE = "INFERÊNCIA"
    ESTIMATE = "ESTIMATIVA"
    PROJECTION = "PROJEÇÃO"
    HYPOTHESIS = "HIPÓTESE"
    MODEL_OPINION = "OPINIÃO_DO_MODELO"


class ScenarioOption(BaseModel):
    option_id: str
    cost: float = Field(ge=0, le=1)
    time: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)
    benefit: float = Field(ge=0, le=1)
    dependency_burden: float = Field(ge=0, le=1)
    reversibility: float = Field(ge=0, le=1)
    impact: float = Field(ge=0, le=1)


class ScenarioResult(BaseModel):
    recommended_option: str
    score: float
    confidence: float
    assumptions: list[str]
    risks: list[str]


class ScenarioEngine:
    def compare(self, options: list[ScenarioOption]) -> ScenarioResult:
        if not options:
            raise ValueError("at least one scenario option is required")

        def score(option: ScenarioOption) -> float:
            positive = 0.35 * option.benefit + 0.25 * option.impact + 0.15 * option.reversibility
            negative = (
                0.1 * option.cost
                + 0.05 * option.time
                + 0.07 * option.risk
                + 0.03 * option.dependency_burden
            )
            return positive - negative

        ranked = sorted(((score(o), o) for o in options), key=lambda item: item[0], reverse=True)
        best_score, best = ranked[0]
        gap = best_score - ranked[1][0] if len(ranked) > 1 else 0.25
        confidence = min(0.95, max(0.3, 0.55 + gap))
        return ScenarioResult(
            recommended_option=best.option_id,
            score=round(best_score, 4),
            confidence=round(confidence, 4),
            assumptions=["inputs are normalized to 0..1", "weights are policy defaults"],
            risks=["decision quality depends on input quality"],
        )


class Hypothesis(BaseModel):
    hypothesis_id: str = Field(default_factory=lambda: uuid4().hex)
    statement: str
    mechanism: str
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    test: str
    confidence: float = Field(default=0.25, ge=0, le=1)
    status: str = "PROPOSED"
    epistemic_type: EpistemicType = EpistemicType.HYPOTHESIS


class HypothesisEngine:
    def create(self, *, statement: str, mechanism: str, test: str) -> Hypothesis:
        if not statement.strip() or not test.strip():
            raise ValueError("hypothesis statement and test are required")
        return Hypothesis(statement=statement, mechanism=mechanism, test=test)
