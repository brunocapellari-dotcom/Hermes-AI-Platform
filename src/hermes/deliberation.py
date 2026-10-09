from __future__ import annotations

from pydantic import BaseModel, Field


class DeliberationCandidate(BaseModel):
    candidate_id: str
    model_id: str
    output: str
    confidence: float = Field(ge=0, le=1)
    evaluation_score: float = Field(ge=0, le=1)
    evidence_count: int = Field(default=0, ge=0)
    policy_allowed: bool = True
    tests_passed: bool = True
    independent: bool = True


class DeliberationScore(BaseModel):
    candidate_id: str
    score: float = Field(ge=0, le=1)
    eligible: bool
    reasons: list[str] = Field(default_factory=list)


class DeliberationDecision(BaseModel):
    selected_candidate_id: str | None = None
    scores: list[DeliberationScore]
    quorum_met: bool
    disagreement: bool
    requires_review: bool


class DeliberationEngine:
    def __init__(self, minimum_quorum: int = 2, disagreement_margin: float = 0.06) -> None:
        if minimum_quorum < 1:
            raise ValueError("minimum_quorum must be positive")
        if not 0 <= disagreement_margin <= 1:
            raise ValueError("disagreement_margin must be between 0 and 1")
        self.minimum_quorum = minimum_quorum
        self.disagreement_margin = disagreement_margin

    def decide(self, candidates: list[DeliberationCandidate]) -> DeliberationDecision:
        scores: list[DeliberationScore] = []
        for candidate in candidates:
            eligible = candidate.policy_allowed and candidate.tests_passed and bool(candidate.output.strip())
            evidence_score = min(candidate.evidence_count / 5.0, 1.0)
            score = (
                candidate.evaluation_score * 0.45
                + candidate.confidence * 0.30
                + evidence_score * 0.15
                + (0.10 if candidate.independent else 0.0)
            )
            reasons: list[str] = []
            if not candidate.policy_allowed:
                reasons.append("policy denied")
            if not candidate.tests_passed:
                reasons.append("verification failed")
            if not candidate.output.strip():
                reasons.append("empty output")
            if candidate.independent:
                reasons.append("independent candidate")
            scores.append(
                DeliberationScore(
                    candidate_id=candidate.candidate_id,
                    score=round(score if eligible else 0.0, 4),
                    eligible=eligible,
                    reasons=reasons,
                )
            )

        ranked = sorted((item for item in scores if item.eligible), key=lambda item: item.score, reverse=True)
        quorum_met = len(ranked) >= self.minimum_quorum
        disagreement = False
        selected: str | None = ranked[0].candidate_id if ranked else None
        if len(ranked) >= 2:
            top = next(item for item in candidates if item.candidate_id == ranked[0].candidate_id)
            second = next(item for item in candidates if item.candidate_id == ranked[1].candidate_id)
            close_scores = abs(ranked[0].score - ranked[1].score) <= self.disagreement_margin
            different_outputs = top.output.strip().casefold() != second.output.strip().casefold()
            disagreement = close_scores and different_outputs
        requires_review = not quorum_met or disagreement or selected is None
        return DeliberationDecision(
            selected_candidate_id=selected,
            scores=scores,
            quorum_met=quorum_met,
            disagreement=disagreement,
            requires_review=requires_review,
        )
