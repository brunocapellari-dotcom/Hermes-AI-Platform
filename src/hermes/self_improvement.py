from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from hermes.registry import RegistryKind, SqlRegistry


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
            ImprovementStage.PROMOTED
            if index == len(self.ORDER) - 1
            else self.ORDER[index + 1]
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


class PersistentImprovementEngine:
    """Persisted state machine; caller-supplied stage never overrides stored state."""

    def __init__(self, registry: SqlRegistry) -> None:
        self.registry = registry
        self.engine = ControlledImprovementEngine()

    def _save(self, proposal: ImprovementProposal) -> ImprovementProposal:
        self.registry.upsert(
            RegistryKind.IMPROVEMENT,
            proposal.proposal_id,
            proposal.model_dump(mode="json"),
            status=proposal.stage.value,
        )
        return proposal

    def get(self, proposal_id: str) -> ImprovementProposal | None:
        item = self.registry.get(RegistryKind.IMPROVEMENT, proposal_id)
        if item is None:
            return None
        return ImprovementProposal.model_validate(item.payload)

    def propose(self, proposal: ImprovementProposal) -> ImprovementProposal:
        if proposal.stage != ImprovementStage.PROPOSED:
            raise ValueError("new improvements must begin at PROPOSED")
        if self.get(proposal.proposal_id) is not None:
            raise ValueError("improvement proposal already exists")
        return self._save(proposal)

    def advance(self, submitted: ImprovementProposal) -> ImprovementProposal:
        current = self.get(submitted.proposal_id)
        if current is None:
            current = self.propose(
                submitted.model_copy(update={"stage": ImprovementStage.PROPOSED})
            )
        if current.target != submitted.target or current.description != submitted.description:
            raise ValueError("improvement target and description are immutable")
        current.tests_passed = current.tests_passed or submitted.tests_passed
        current.benchmark_improved = (
            current.benchmark_improved or submitted.benchmark_improved
        )
        current.independent_audit_passed = (
            current.independent_audit_passed or submitted.independent_audit_passed
        )
        if current.previous_version is None:
            current.previous_version = submitted.previous_version
        if current.proposed_version is None:
            current.proposed_version = submitted.proposed_version
        return self._save(self.engine.advance(current))

    def reject(self, proposal_id: str) -> ImprovementProposal:
        current = self.get(proposal_id)
        if current is None:
            raise KeyError(proposal_id)
        if current.stage in {
            ImprovementStage.PROMOTED,
            ImprovementStage.ROLLED_BACK,
            ImprovementStage.REJECTED,
        }:
            raise ValueError(f"stage cannot reject: {current.stage}")
        return self._save(self.engine.reject(current))

    def rollback(self, proposal_id: str) -> ImprovementProposal:
        current = self.get(proposal_id)
        if current is None:
            raise KeyError(proposal_id)
        return self._save(self.engine.rollback(current))
