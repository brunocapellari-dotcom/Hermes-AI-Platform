from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from hermes.cognitive import HybridIntentEngine, TaskGraphPlanner
from hermes.config import Settings, get_settings
from hermes.domain import ModelProfile, ModelRouteRequest, PolicyRequest, TrustLevel
from hermes.factories import AgentFactory, SkillFactory
from hermes.hardware import discover_hardware, recommend_local_runtime
from hermes.integrations import OpenAICompatibleGateway, ResearchClient, SecondBrainClient
from hermes.orchestrator import HermesOrchestrator
from hermes.persistence import Database, SqlAuditSink, SqlMissionStore
from hermes.routing import ModelRouter, ProjectRouter
from hermes.security import DefaultPolicyEngine, PromptInjectionDetector


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


class AppContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.database_url)
        if settings.auto_create_schema or not settings.is_production:
            self.db.create_schema()
        gateway = None
        api_key = settings.model_gateway_api_key.get_secret_value() if settings.model_gateway_api_key else None
        if settings.model_gateway_url:
            gateway = OpenAICompatibleGateway(
                settings.model_gateway_url, api_key=api_key, timeout=settings.request_timeout_seconds
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
            mission_store=SqlMissionStore(self.db),
            audit=SqlAuditSink(self.db),
            knowledge=knowledge,
            research=research,
        )
        self.mission_store = SqlMissionStore(self.db)
        self.audit = SqlAuditSink(self.db)
        self.policy = DefaultPolicyEngine(allow_external_actions=settings.allow_external_actions)
        self.injection = PromptInjectionDetector()
        self.model_router = ModelRouter([])


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    container = AppContainer(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
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

    @api.get("/v1/models")
    def models() -> list[dict[str, Any]]:
        return [m.model_dump(mode="json") for m in container.model_router.models]

    return api


app = create_app()
