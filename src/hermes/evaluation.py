from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field


class EvalCase(BaseModel):
    case_id: str
    prompt: str
    expected_contains: list[str] = Field(default_factory=list)
    forbidden_contains: list[str] = Field(default_factory=list)
    minimum_length: int = Field(default=1, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    case_id: str
    passed: bool
    score: float = Field(ge=0, le=1)
    failures: list[str] = Field(default_factory=list)
    output: str


class EvalSummary(BaseModel):
    total: int
    passed: int
    pass_rate: float = Field(ge=0, le=1)
    average_score: float = Field(ge=0, le=1)
    results: list[EvalResult]


class EvaluationLab:
    def score(self, case: EvalCase, output: str) -> EvalResult:
        checks = 1 + len(case.expected_contains) + len(case.forbidden_contains)
        passed_checks = 0
        failures: list[str] = []
        if len(output.strip()) >= case.minimum_length:
            passed_checks += 1
        else:
            failures.append("minimum_length")
        lowered = output.lower()
        for expected in case.expected_contains:
            if expected.lower() in lowered:
                passed_checks += 1
            else:
                failures.append(f"missing:{expected}")
        for forbidden in case.forbidden_contains:
            if forbidden.lower() not in lowered:
                passed_checks += 1
            else:
                failures.append(f"forbidden:{forbidden}")
        score = passed_checks / checks if checks else 1.0
        return EvalResult(
            case_id=case.case_id,
            passed=not failures,
            score=round(score, 4),
            failures=failures,
            output=output,
        )

    def run(self, cases: list[EvalCase], executor: Callable[[str], str]) -> EvalSummary:
        results = [self.score(case, executor(case.prompt)) for case in cases]
        passed = sum(result.passed for result in results)
        average = sum(result.score for result in results) / len(results) if results else 0.0
        return EvalSummary(
            total=len(results),
            passed=passed,
            pass_rate=round(passed / len(results), 4) if results else 0.0,
            average_score=round(average, 4),
            results=results,
        )


class ReviewInput(BaseModel):
    output: str
    evidence_count: int = Field(default=0, ge=0)
    confidence: float = Field(default=0, ge=0, le=1)
    policy_allowed: bool = True
    tests_passed: bool = True
    expected_claims: list[str] = Field(default_factory=list)


class ReviewReport(BaseModel):
    role: str
    passed: bool
    findings: list[str] = Field(default_factory=list)


class Critic:
    def review(self, item: ReviewInput) -> ReviewReport:
        findings: list[str] = []
        if not item.output.strip():
            findings.append("empty output")
        if item.confidence >= 0.8 and item.evidence_count == 0:
            findings.append("high confidence without evidence")
        lowered = item.output.lower()
        for claim in item.expected_claims:
            if claim.lower() not in lowered:
                findings.append(f"expected claim absent: {claim}")
        return ReviewReport(role="critic", passed=not findings, findings=findings)


class Judge:
    def review(self, item: ReviewInput) -> ReviewReport:
        findings: list[str] = []
        if not item.policy_allowed:
            findings.append("policy denied output/action")
        if not item.tests_passed:
            findings.append("required tests failed")
        if item.confidence < 0.5 and item.evidence_count:
            findings.append("low-confidence evidence synthesis")
        return ReviewReport(role="judge", passed=not findings, findings=findings)


class Auditor:
    def review(self, item: ReviewInput) -> ReviewReport:
        findings: list[str] = []
        if item.evidence_count == 0 and item.expected_claims:
            findings.append("claims require evidence")
        if not item.policy_allowed:
            findings.append("authorization boundary failed")
        if not item.tests_passed:
            findings.append("verification boundary failed")
        return ReviewReport(role="auditor", passed=not findings, findings=findings)


class ReviewPanel:
    def review(self, item: ReviewInput) -> list[ReviewReport]:
        return [Critic().review(item), Judge().review(item), Auditor().review(item)]

    def approved(self, item: ReviewInput) -> bool:
        return all(report.passed for report in self.review(item))
