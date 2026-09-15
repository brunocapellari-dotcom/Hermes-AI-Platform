from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrustLevel(StrEnum):
    SYSTEM = "system"
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class MissionStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionType(StrEnum):
    QUERY = "query"
    ANALYZE = "analyze"
    RESEARCH = "research"
    CREATE = "create"
    EXECUTE = "execute"
    UPDATE = "update"
    DELETE = "delete"

    @property
    def mutating(self) -> bool:
        return self in {self.CREATE, self.EXECUTE, self.UPDATE, self.DELETE}


class KnowledgeStatus(StrEnum):
    PROPOSED = "PROPOSTO"
    IN_REVIEW = "EM_REVISÃO"
    VALIDATED = "VALIDADO"
    CANONICAL = "CANÔNICO"
    CONFLICTING = "CONFLITANTE"
    SUPERSEDED = "SUPERADO"
    REJECTED = "REJEITADO"


class ModelClass(StrEnum):
    FAST = "FAST"
    CHEAP = "CHEAP"
    ROUTINE = "ROUTINE"
    PRIVATE = "PRIVATE"
    OFFLINE = "OFFLINE"
    REASONING = "REASONING"
    DEEP_REASONING = "DEEP_REASONING"
    RESEARCH = "RESEARCH"
    CODING = "CODING"
    LONG_CONTEXT = "LONG_CONTEXT"
    VISION = "VISION"
    AUDIO = "AUDIO"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    AUDIT = "AUDIT"
    CRITICAL_REVIEW = "CRITICAL_REVIEW"


class Intent(BaseModel):
    explicit_request: str
    goal: str
    capabilities: list[str] = Field(default_factory=list)
    probable_projects: list[str] = Field(default_factory=list)
    action_type: ActionType = ActionType.ANALYZE
    urgency: int = Field(default=1, ge=1, le=5)
    risk: RiskLevel = RiskLevel.LOW
    requires_external_action: bool = False
    requires_research: bool = False
    private_only: bool = False


class TaskNode(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    capability: str
    project: str | None = None
    action_type: ActionType = ActionType.ANALYZE
    dependencies: list[str] = Field(default_factory=list)
    expected_output: str
    risk: RiskLevel = RiskLevel.LOW
    status: TaskStatus = TaskStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)


class Mission(BaseModel):
    mission_id: str = Field(default_factory=lambda: uuid4().hex)
    goal: str
    intent: Intent
    tasks: list[TaskNode]
    status: MissionStatus = MissionStatus.PLANNED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    checkpoints: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelProfile(BaseModel):
    model_id: str
    provider: str
    model: str
    version: str | None = None
    deployment: str | None = None
    privacy_tier: str = "standard"
    status: str = "active"
    classes: set[ModelClass]
    context_window: int = 0
    supports_tools: bool = False
    supports_structured_output: bool = False
    supports_vision: bool = False
    supports_audio: bool = False
    local: bool = False
    input_cost_per_million: float = Field(default=0.0, ge=0)
    output_cost_per_million: float = Field(default=0.0, ge=0)
    cost_score: float = Field(default=0.5, ge=0, le=1)
    latency_score: float = Field(default=0.5, ge=0, le=1)
    quality_score: float = Field(default=0.5, ge=0, le=1)
    benchmark_score: float = Field(default=0.5, ge=0, le=1)
    benchmark_source: str | None = None
    last_evaluated_at: datetime | None = None
    available: bool = True


class ModelRouteRequest(BaseModel):
    required_classes: set[ModelClass] = Field(default_factory=set)
    private_only: bool = False
    minimum_context: int = 0
    require_tools: bool = False
    require_structured_output: bool = False
    quality_priority: float = Field(default=0.5, ge=0, le=1)
    latency_priority: float = Field(default=0.25, ge=0, le=1)
    cost_priority: float = Field(default=0.25, ge=0, le=1)


class RouteDecision(BaseModel):
    model_id: str
    score: float
    reasons: list[str]


class Evidence(BaseModel):
    claim: str
    source: str
    confidence: float = Field(ge=0, le=1)
    status: KnowledgeStatus
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    reference_date: datetime | None = None
    publication_date: datetime | None = None
    collected_at: datetime | None = None


class PermissionSet(BaseModel):
    read_scopes: list[str] = Field(default_factory=list)
    write: bool = False
    external_actions: bool = False
    secrets: list[str] = Field(default_factory=list)
    money: bool = False
    production_admin: bool = False


class AgentSpec(BaseModel):
    agent_id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    project: str
    mission: str
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    permissions: PermissionSet = Field(default_factory=PermissionSet)
    autonomy_level: int = Field(default=0, ge=0, le=6)
    risk: RiskLevel = RiskLevel.LOW
    status: str = "sandbox"


class SkillSpec(BaseModel):
    skill_id: str = Field(default_factory=lambda: uuid4().hex)
    purpose: str
    inputs: list[str]
    outputs: list[str]
    procedure: list[str]
    tools: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    version: str = "0.1.0"


class ToolSpec(BaseModel):
    tool_id: str
    owner: str
    project: str | None = None
    permissions: PermissionSet = Field(default_factory=PermissionSet)
    risk: RiskLevel = RiskLevel.LOW
    timeout_seconds: float = 30.0
    rate_limit_per_minute: int = 60


class PolicyRequest(BaseModel):
    actor: str
    subject: str | None = None
    action: str
    resource: str | None = None
    relation: str | None = None
    risk: RiskLevel
    trust: TrustLevel = TrustLevel.TRUSTED
    external_write: bool = False
    money: bool = False
    production_admin: bool = False
    requests_scope_increase: bool = False


class PolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool = False
    reason: str


class HardwareProfile(BaseModel):
    cpu_count: int
    ram_bytes: int | None = None
    gpu_present: bool = False
    gpu_name: str | None = None
    vram_bytes: int | None = None
    cuda_available: bool = False
    rocm_available: bool = False
    os: str
    architecture: str
