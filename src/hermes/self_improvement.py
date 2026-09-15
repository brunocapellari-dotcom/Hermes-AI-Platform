from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class ImprovementStage(StrEnum):
    CURRENT = "CURRENT"
    PROPOSED = "PROPOSED"
    SANDBOX = "SANDBOX"
    TESTS = "TESTS"
    BENCHMARK = "BENCHMARK"
    AB = "A/B"
    AUDIT = "AUDIT"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


class ImprovementProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: uuid4().hex)
    target: str
    description: str
    stage: ImprovementStage = ImprovementStage.PROPOSED
    tests_passed: bool = False
    benchmark_improved: bool = False
    independent_audit_passed: bool = False
    previous_version: str | None = None
    proposed_version: str | None = None


class ControlledImprovementEngine:
    ORDER = [
        ImprovementStage.PROPOSED,
        ImprovementStage.SANDBOX,
        ImprovementStage.TESTS,
        ImprovementStage.BENCHMARK,
        ImprovementStage.AB,
        ImprovementStage.AUDIT,
    ]

    def advance(self, proposal: ImprovementProposal) -> ImprovementProposal:
        if proposal.stage not in self.ORDER:
            raise ValueError(f"stage cannot advance: {proposal.stage}")
        index = self.ORDER.index(proposal.stage)
        if proposal.stage == ImprovementStage.TESTS and not proposal.tests_passed:
            raise ValueError("tests must pass before benchmark")
        if proposal.stage == ImprovementStage.BENCHMARK and not proposal.benchmark_improved:
            raise ValueError("benchmark must improve before A/B")
        if proposal.stage == ImprovementStage.AUDIT and not proposal.independent_audit_passed:
            raise ValueError("independent audit must pass before promotion")
        proposal.stage = (
            ImprovementStage.PROMOTED if index == len(self.ORDER) - 1 else self.ORDER[index + 1]
        )
        return proposal

    def reject(self, proposal: ImprovementProposal) -> ImprovementProposal:
        proposal.stage = ImprovementStage.REJECTED
        return proposal

    def rollback(self, proposal: ImprovementProposal) -> ImprovementProposal:
        if proposal.stage != ImprovementStage.PROMOTED or not proposal.previous_version:
            raise ValueError("only promoted changes with a previous version can roll back")
        proposal.stage = ImprovementStage.ROLLED_BACK
        return proposal
