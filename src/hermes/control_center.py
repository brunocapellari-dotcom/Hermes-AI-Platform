from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from hermes.ecosystem import CANONICAL_PROJECTS, ProjectContractValidator
from hermes.proactive import DailyIntelligence, DailyIntelligenceBuilder
from hermes.registry import RegistryKind, SqlRegistry
from hermes.world_state import WorldState, WorldStateBuilder


class ControlCenterSnapshot(BaseModel):
    world_state: WorldState
    daily_intelligence: DailyIntelligence
    project_contract_coverage: dict[str, bool]
    registered_projects: int
    canonical_projects: int
    operational_ratio: float


class ControlCenter:
    def __init__(self, world_state: WorldStateBuilder, registry: SqlRegistry) -> None:
        self.world_state = world_state
        self.registry = registry

    def snapshot(self) -> ControlCenterSnapshot:
        state = self.world_state.snapshot()
        items = self.registry.list(RegistryKind.PROJECT)
        registrations: dict[str, dict[str, Any]] = {item.item_id: item.payload for item in items}
        coverage = ProjectContractValidator().coverage(registrations)
        operational = sum(coverage.values())
        total = len(coverage)
        return ControlCenterSnapshot(
            world_state=state,
            daily_intelligence=DailyIntelligenceBuilder().build(state),
            project_contract_coverage=coverage,
            registered_projects=len(items),
            canonical_projects=len(CANONICAL_PROJECTS),
            operational_ratio=round(operational / total, 4) if total else 0.0,
        )
