from __future__ import annotations

from pydantic import BaseModel, Field


class DelegationFrame(BaseModel):
    project: str
    agent: str
    capability: str


class DelegationTrace(BaseModel):
    frames: list[DelegationFrame] = Field(default_factory=list)


class DelegationGuard:
    def __init__(self, *, max_depth: int = 8, max_nodes: int = 64) -> None:
        if max_depth < 1 or max_depth > 32:
            raise ValueError("max_depth must be between 1 and 32")
        if max_nodes < max_depth or max_nodes > 1024:
            raise ValueError("max_nodes must be >= max_depth and <= 1024")
        self.max_depth = max_depth
        self.max_nodes = max_nodes

    def enter(
        self,
        trace: DelegationTrace,
        *,
        project: str,
        agent: str,
        capability: str,
    ) -> DelegationTrace:
        if len(trace.frames) >= self.max_depth:
            raise RuntimeError("delegation depth limit exceeded")
        if len(trace.frames) >= self.max_nodes:
            raise RuntimeError("delegation node budget exhausted")
        frame = DelegationFrame(project=project, agent=agent, capability=capability)
        if frame in trace.frames:
            raise RuntimeError("recursive delegation loop detected")
        return trace.model_copy(update={"frames": [*trace.frames, frame]})
