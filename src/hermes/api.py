from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from hermes.ai_core import AIService
from hermes.cognitive import HybridIntentEngine, TaskGraphPlanner
from hermes.config import Settings, get_settings
from hermes.context import ContextItem, ContextRouter
from hermes.decision import HypothesisEngine, ScenarioEngine, ScenarioOption
from hermes.domain import ModelClass, ModelRouteRequest, PolicyRequest, TrustLevel
from hermes.durable import DBOSMissionDispatcher
from hermes.factories import AgentFactory, SkillFactory
from hermes.hardware import discover_hardware, recommend_local_runtime
from hermes.integrations import OpenAICompatibleGateway, ResearchClient, SecondBrainClient
from hermes.orchestrator import HermesOrchestrator
from hermes.persistence import Database, SqlAuditSink, SqlMissionStore
from hermes.registry import PersistentModelRegistry, SqlRegistry
from hermes.routing import ModelRouter, ProjectRouter
from hermes.security import DefaultPolicyEngine, PromptInjectionDetector
from hermes.self_improvement import ControlledImprovementEngine, ImprovementProposal
from hermes.telemetry import SqlUsageStore, prometheus_payload
from hermes.world_state import WorldStateBuilder


class MissionCreate(BaseModel):
    request: str = Field(min_length=1, max_length=20_000)
    actor: str = "owner"


class InjectionInspect(BaseModel):
    content: str
    trust: TrustLevel = TrustLevel.UNTRUSTED


class AgentCreateSpec(BaseModel):
    name: str
    project: str
    mission: str
    read_scopes: list[str] = Field(default_factory=list)


class SkillCreateSpec(BaseModel):
    purpose: str
    inputs: list[str]
    outputs: list[str]
    procedure: list[str]
    validation: list[str]


class HypothesisCreate(BaseModel):
    statement: str
    mechanism: str
    test: str


class ScenarioCompare(BaseModel):
    options: list[ScenarioOption]


class ContextSelect(BaseModel):
    items: list[ContextItem]
    target_project: str
    tenant: str = "owner"


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)
    private_only: bool = False
    mission_id: str | None = None
    project: str | None = None


class AppContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.database_url)
        # SQLite is strictly a local/test fallback and has no external migration plane.
        # Managed production databases keep schema creation explicit.
        if (
            settings.auto_create_schema
            or not settings.is_production
            or settings.database_url.startswith("sqlite")
        ):
            self.db.create_schema()
        self.mission_store = SqlMissionStore(self.db)
        self.audit = SqlAuditSink(self.db)
        self.registry = SqlRegistry(self.db)
        self.models = PersistentModelRegistry(self.registry)
        self.usage = SqlUsageStore(self.db)
        self.world_state = WorldStateBuilder(
            self.registry, self.mission_store, self.audit, self.usage
        )
        gateway = None
        api_key = (
            settings.model_gateway_api_key.get_secret_value()
            if settings.model_gateway_api_key
            else None
        )
        if settings.model_gateway_url:
            gateway = OpenAICompatibleGateway(
                settings.model_gateway_url,
                api_key=api_key,
                timeout=settings.request_timeout_seconds,
            )
        knowledge = (
            SecondBrainClient(settings.second_brain_url, settings.request_timeout_seconds)
            if settings.second_brain_url
            else None
        )
        research = (
            ResearchClient(settings.research_url, settings.request_timeout_seconds)
            if settings.research_url
            else None
        )
        self.orchestrator = HermesOrchestrator(
            intent_engine=HybridIntentEngine(gateway, settings.default_model),
            planner=TaskGraphPlanner(),
            project_router=ProjectRouter(),
            mission_store=self.mission_store,
            audit=self.audit,
            knowledge=knowledge,
            research=research,
        )
        self.policy = DefaultPolicyEngine(allow_external_actions=settings.allow_external_actions)
        self.injection = PromptInjectionDetector()
        self.model_router = ModelRouter(self.models.load())
        self.ai = (
            AIService(gateway=gateway, router=self.model_router, usage=self.usage)
            if gateway is not None
            else None
        )
        self.durable = (
            DBOSMissionDispatcher(
                settings.dbos_system_database_url,
                application_name=settings.dbos_application_name,
                queue_name=settings.dbos_queue_name,
            )
            if settings.dbos_system_database_url
            else None
        )
        self.context = ContextRouter()
        self.scenarios = ScenarioEngine()
        self.hypotheses = HypothesisEngine()
        self.improvements = ControlledImprovementEngine()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    container = AppContainer(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield

    api = FastAPI(title="Hermes AI Platform", version="0.1.0", lifespan=lifespan)
    api.state.container = container

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "hermes-ai-platform"}

    @api.get("/ready")
    def ready() -> dict[str, str]:
        with container.db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}

    @api.get("/v1/capabilities")
    def capabilities() -> dict[str, Any]:
        return {
            "capabilities": [
                "mission_planning",
                "model_routing",
                "context_routing",
                "agent_specification",
                "skill_specification",
                "scenario_comparison",
                "hypothesis_creation",
                "world_state",
            ],
            "ai_generation_configured": container.ai is not None,
            "durable_dispatch_configured": container.durable is not None,
        }

    @api.post("/v1/missions")
    async def create_mission(payload: MissionCreate) -> dict[str, Any]:
        mission = await container.orchestrator.create_mission(payload.request, actor=payload.actor)
        return mission.model_dump(mode="json")

    @api.get("/v1/missions/{mission_id}")
    def get_mission(mission_id: str) -> dict[str, Any]:
        mission = container.mission_store.get(mission_id)
        if mission is None:
            raise HTTPException(status_code=404, detail="mission not found")
        return mission.model_dump(mode="json")

    @api.post("/v1/missions/{mission_id}/dispatch")
    def dispatch_mission(mission_id: str) -> dict[str, str]:
        if container.mission_store.get(mission_id) is None:
            raise HTTPException(status_code=404, detail="mission not found")
        if container.durable is None:
            raise HTTPException(status_code=503, detail="durable execution not configured")
        workflow_id = container.durable.enqueue(mission_id)
        container.audit.record(
            "mission.dispatched", "owner", {"mission_id": mission_id, "workflow_id": workflow_id}
        )
        return {"mission_id": mission_id, "workflow_id": workflow_id}

    @api.post("/v1/chat")
    async def chat(payload: GenerateRequest) -> dict[str, Any]:
        if container.ai is None:
            raise HTTPException(status_code=503, detail="model gateway not configured")
        result = await container.ai.generate(
            request=ModelRouteRequest(
                required_classes={ModelClass.ROUTINE}, private_only=payload.private_only
            ),
            system="You are Hermes. Respect policy and epistemic boundaries.",
            user=payload.prompt,
            mission_id=payload.mission_id,
            project=payload.project,
        )
        return {
            "content": result.content,
            "model_id": result.route.model_id,
            "route_score": result.route.score,
            "attempts": result.attempts,
        }

    @api.post("/v1/reason")
    async def reason(payload: GenerateRequest) -> dict[str, Any]:
        if container.ai is None:
            raise HTTPException(status_code=503, detail="model gateway not configured")
        result = await container.ai.generate(
            request=ModelRouteRequest(
                required_classes={ModelClass.REASONING}, private_only=payload.private_only
            ),
            system="Reason carefully. Separate fact, inference, estimate, projection and hypothesis.",
            user=payload.prompt,
            mission_id=payload.mission_id,
            project=payload.project,
        )
        return {
            "content": result.content,
            "model_id": result.route.model_id,
            "route_score": result.route.score,
            "attempts": result.attempts,
        }

    @api.post("/v1/embed", status_code=503)
    def embed_unconfigured() -> dict[str, str]:
        return {"status": "unconfigured", "detail": "embedding service adapter not configured"}

    @api.post("/v1/vision", status_code=503)
    def vision_unconfigured() -> dict[str, str]:
        return {"status": "unconfigured", "detail": "vision service adapter not configured"}

    @api.post("/v1/audio/transcribe", status_code=503)
    def transcribe_unconfigured() -> dict[str, str]:
        return {"status": "unconfigured", "detail": "STT service adapter not configured"}

    @api.post("/v1/audio/speech", status_code=503)
    def speech_unconfigured() -> dict[str, str]:
        return {"status": "unconfigured", "detail": "TTS service adapter not configured"}

    @api.post("/v1/security/inspect")
    def inspect(payload: InjectionInspect) -> dict[str, Any]:
        return container.injection.inspect(payload.content, trust=payload.trust)

    @api.post("/v1/security/authorize")
    def authorize(payload: PolicyRequest) -> dict[str, Any]:
        return container.policy.authorize(payload).model_dump()

    @api.post("/v1/models/route")
    def route_model(payload: ModelRouteRequest) -> dict[str, Any]:
        try:
            return container.model_router.route(payload).model_dump()
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.get("/v1/models")
    def models() -> list[dict[str, Any]]:
        return [m.model_dump(mode="json") for m in container.model_router.models]

    @api.get("/v1/hardware")
    def hardware() -> dict[str, Any]:
        profile = discover_hardware()
        return {"profile": profile.model_dump(), "recommendation": recommend_local_runtime(profile)}

    @api.post("/v1/agents/spec")
    def agent_spec(payload: AgentCreateSpec) -> dict[str, Any]:
        return AgentFactory().specification(**payload.model_dump()).model_dump()

    @api.post("/v1/skills/spec")
    def skill_spec(payload: SkillCreateSpec) -> dict[str, Any]:
        return SkillFactory().specification(**payload.model_dump()).model_dump()

    @api.post("/v1/context/select")
    def context_select(payload: ContextSelect) -> dict[str, Any]:
        selected = container.context.select(
            payload.items, target_project=payload.target_project, tenant=payload.tenant
        )
        return {"items": [item.model_dump(mode="json") for item in selected]}

    @api.post("/v1/scenarios/compare")
    def compare_scenarios(payload: ScenarioCompare) -> dict[str, Any]:
        return container.scenarios.compare(payload.options).model_dump()

    @api.post("/v1/hypotheses")
    def create_hypothesis(payload: HypothesisCreate) -> dict[str, Any]:
        return container.hypotheses.create(**payload.model_dump()).model_dump(mode="json")

    @api.post("/v1/improvements/advance")
    def advance_improvement(payload: ImprovementProposal) -> dict[str, Any]:
        try:
            return container.improvements.advance(payload).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.get("/v1/world-state")
    def world_state() -> dict[str, Any]:
        return container.world_state.snapshot().model_dump(mode="json")

    @api.get("/v1/telemetry/summary")
    def telemetry_summary() -> dict[str, Any]:
        return container.usage.summary()

    @api.get("/metrics")
    def metrics() -> Response:
        body, content_type = prometheus_payload()
        return Response(content=body, media_type=content_type)

    return api


app = create_app()
