"""Canonical Hermes manifest contracts.

Pydantic models are the schema source of truth. JSON Schema files under
`schemas/` are generated artifacts and must not be edited by hand.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExternalContentTrust(StrEnum):
    UNTRUSTED = "untrusted"
    MIXED = "mixed"
    TRUSTED = "trusted"


class SideEffects(StrEnum):
    NONE = "none"
    REVERSIBLE = "reversible"
    EXTERNAL = "external"
    IRREVERSIBLE = "irreversible"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalPolicy(StrEnum):
    ALLOW = "allow"
    POLICY = "policy"
    HUMAN = "human"
    DENY = "deny"


class CostClass(StrEnum):
    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentEntry(StrictModel):
    channels: list[str] = Field(default_factory=list)
    accepted_inputs: list[str] = Field(default_factory=list)


class AgentInstructions(StrictModel):
    mission: str = Field(min_length=1)
    objectives: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


class AgentKnowledge(StrictModel):
    canonical_sources: list[str] = Field(default_factory=list)
    retrieval_sources: list[str] = Field(default_factory=list)
    external_content_trust: ExternalContentTrust = ExternalContentTrust.UNTRUSTED


class AgentToolGrant(StrictModel):
    tool_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$")
    scopes: list[str] = Field(default_factory=list)
    read_only: bool = True


class AgentTriggers(StrictModel):
    events: list[str] = Field(default_factory=list)
    schedules: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)


class AgentLimits(StrictModel):
    prohibited_actions: list[str] = Field(default_factory=list)
    approval_required: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = Field(default=None, ge=1)
    budget: float | None = Field(default=None, ge=0)
    rate_limit_per_minute: int | None = Field(default=None, ge=1)


class AgentManifest(StrictModel):
    agent_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$")
    version: str = Field(min_length=1)
    project_id: str | None = None
    owner: str | None = None
    entry: AgentEntry
    instructions: AgentInstructions
    knowledge: AgentKnowledge
    tools: list[AgentToolGrant] = Field(default_factory=list)
    triggers: AgentTriggers = Field(default_factory=AgentTriggers)
    limits: AgentLimits


class ToolManifest(StrictModel):
    tool_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$")
    version: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    project: str = Field(min_length=1)
    read_only: bool
    side_effects: SideEffects
    required_scopes: list[str] = Field(default_factory=list)
    risk_level: RiskLevel
    timeout_seconds: int | None = Field(default=None, ge=1)
    cost_class: CostClass | None = None
    approval_policy: ApprovalPolicy = ApprovalPolicy.POLICY
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    provenance_required: bool = True
