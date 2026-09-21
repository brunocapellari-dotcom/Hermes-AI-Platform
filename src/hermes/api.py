from __future__ import annotations

import base64
import binascii
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from hermes.ai_core import AIService
from hermes.auth import authenticated_actor
from hermes.architecture_policy import (
    PLATFORM_COMPONENT_DECISIONS,
    PYDANTIC_HARNESS_DECISIONS,
)
from hermes.authorization import build_policy_engine
from hermes.cloud_sql import close_cloud_sql_resources
from hermes.cognitive import HybridIntentEngine, TaskGraphPlanner
from hermes.config import Settings, get_settings
from hermes.context import ContextItem, ContextRouter
from hermes.contracts import DurableDispatcher
from hermes.control_center import ControlCenter
from hermes.decision import HypothesisEngine, ScenarioEngine, ScenarioOption
from hermes.domain import AgentSpec, ModelClass, ModelRouteRequest, PolicyRequest, TrustLevel
from hermes.durable import DBOSMissionDispatcher
from hermes.durable_benchmark import CANONICAL_SCENARIOS
from hermes.ecosystem import CANONICAL_PROJECTS, ProjectContractValidator
from hermes.evaluation import EvalCase, EvaluationLab, ReviewInput, ReviewPanel
from hermes.evaluation_strategy import EvaluationPurpose, evaluation_route
from hermes.factories import AgentAuditor, AgentFactory, SkillFactory
from hermes.hardware import discover_hardware, recommend_local_runtime
from hermes.integrations import OpenAICompatibleGateway, ResearchClient, SecondBrainClient
from hermes.model_intelligence import AdaptiveModelRouter, PersistentModelIntelligence
from hermes.mcp_benchmark import MCPBenchmarkTarget, scenarios_for
from hermes.multimodal import OpenAICompatibleMultimodal
from hermes.orchestrator import HermesOrchestrator
from hermes.persistence import Database, SqlAuditSink, SqlMissionStore
from hermes.privacy import SensitiveDataGuard
from hermes.recovery import FailureRecoveryEngine
from hermes.registry import PersistentModelRegistry, RegistryKind, SqlRegistry
from hermes.routing import ProjectRouter
from hermes.security import PromptInjectionDetector
from hermes.self_improvement import ImprovementProposal, PersistentImprovementEngine
from hermes.super_control import SuperControlPlane, build_super_router
from hermes.telemetry import SqlUsageStore, configure_tracing, prometheus_payload
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


class AgentAuditRequest(BaseModel):
    spec: AgentSpec
    tests_passed: bool
    benchmark_passed: bool
    independent_review_passed: bool
    external_action_approved: bool = False


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


class EmbedRequest(BaseModel):
    inputs: list[str] = Field(min_length=1, max_length=256)


class VisionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    image_url: str = Field(min_length=1, max_length=2_000_000)


class TranscriptionRequest(BaseModel):
    audio_base64: str = Field(min_length=1, max_length=50_000_000)
    filename: str = Field(default="audio.bin", max_length=200)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    voice: str = Field(default="alloy", min_length=1, max_length=100)


class RerankRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    documents: list[str] = Field(min_length=1, max_length=256)


class EvalScoreRequest(BaseModel):
    case: EvalCase
    output: str


class RecoveryRequest(BaseModel):
    error_type: str = ""
    status_code: int | None = Field(default=None, ge=100, le=599)


class ProjectRegistrationRequest(BaseModel):
    key: str
    registration: dict[str, Any]
    persist: bool = False


class AppContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        configure_tracing(settings.otlp_endpoint)
        self.db = Database(settings.database_url)
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
        self.control_center = ControlCenter(self.world_state, self.registry)
        api_key = (
            settings.model_gateway_api_key.get_secret_value()
            if settings.model_gateway_api_key
            else None
        )
        gateway = (
            OpenAICompatibleGateway(
                settings.model_gateway_url,
                api_key=api_key,
                timeout=settings.request_timeout_seconds,
                service_audience=settings.model_gateway_audience,
            )
            if settings.model_gateway_url
            else None
        )
        self.multimodal = (
            OpenAICompatibleMultimodal(
                settings.model_gateway_url,
                api_key=api_key,
                timeout=settings.request_timeout_seconds,
                service_audience=settings.model_gateway_audience,
            )
            if settings.model_gateway_url
            else None
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
        self.policy = build_policy_engine(
            allow_external_actions=settings.allow_external_actions,
            opa_url=settings.opa_url,
            opa_policy_path=settings.opa_policy_path,
            openfga_url=settings.openfga_url,
            openfga_store_id=settings.openfga_store_id,
            openfga_model_id=settings.openfga_model_id,
            opa_audience=settings.opa_audience,
            openfga_audience=settings.openfga_audience,
            external_required=settings.external_authorization_required,
            timeout=settings.authorization_timeout_seconds,
        )
        self.injection = PromptInjectionDetector()
        self.privacy = SensitiveDataGuard()
        self.model_intelligence = PersistentModelIntelligence(self.db)
        self.model_router = AdaptiveModelRouter(self.models.load(), self.model_intelligence)
        self.ai = (
            AIService(
                gateway=gateway,
                router=self.model_router,
                usage=self.usage,
                privacy=self.privacy,
                intelligence=self.model_intelligence,
            )
            if gateway is not None
            else None
        )
        self.super_control = SuperControlPlane(
            registry=self.registry,
            audit=self.audit,
            intelligence=self.model_intelligence,
            privacy=self.privacy,
        )
        self.durable: DurableDispatcher | None = (
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
        self.improvements = PersistentImprovementEngine(self.registry)
        self.evaluation = EvaluationLab()
        self.reviews = ReviewPanel()
        self.recovery = FailureRecoveryEngine()
        self.agent_auditor = AgentAuditor()
        self.project_validator = ProjectContractValidator()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    container = AppContainer(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if container.durable is not None:
                container.durable.close()
            container.db.close()
            close_cloud_sql_resources()

    api = FastAPI(title="Hermes AI Platform", version="0.1.0", lifespan=lifespan)
    api.state.container = container
    api.include_router(build_super_router(container.super_control))

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
                "adaptive_model_routing",
                "model_performance_learning",
                "context_routing",
                "privacy_guard",
                "mcp_admission",
                "deliberation",
                "agent_specification",
                "agent_audit",
                "agent_promotion",
                "skill_specification",
                "skill_promotion",
                "persistent_model_registry",
                "scenario_comparison",
                "hypothesis_creation",
                "evaluation",
                "recovery",
                "world_state",
                "control_center",
                "project_contract_validation",
                "architecture_decisions",
                "durable_engine_benchmark",
                "evaluation_strategy",
                "tool_search",
                "tool_output_limits",
                "embedding",
                "vision",
                "speech_to_text",
                "text_to_speech",
                "rerank",
            ],
            "ai_generation_configured": container.ai is not None,
            "multimodal_configured": container.multimodal is not None,
            "durable_dispatch_configured": container.durable is not None,
            "external_authorization_required": settings.external_authorization_required,
        }

    @api.get("/v1/architecture/components")
    def architecture_components() -> dict[str, Any]:
        return {
            "pydantic_harness": [
                item.model_dump(mode="json") for item in PYDANTIC_HARNESS_DECISIONS
            ],
            "platform_components": [
                item.model_dump(mode="json") for item in PLATFORM_COMPONENT_DECISIONS
            ],
        }

    @api.get("/v1/durable/benchmark/scenarios")
    def durable_benchmark_scenarios() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in CANONICAL_SCENARIOS]

    @api.get("/v1/evaluation/strategy")
    def evaluation_strategy() -> list[dict[str, Any]]:
        return [
            evaluation_route(purpose).model_dump(mode="json")
            for purpose in EvaluationPurpose
        ]

    @api.get("/v1/mcp/benchmark/{target}")
    def mcp_benchmark(target: MCPBenchmarkTarget) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in scenarios_for(target)]

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
            "mission.dispatched",
            authenticated_actor("local-owner") or "local-owner",
            {"mission_id": mission_id, "workflow_id": workflow_id},
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

    @api.post("/v1/embed")
    async def embed(payload: EmbedRequest) -> dict[str, Any]:
        if container.multimodal is None or not settings.embedding_model:
            raise HTTPException(status_code=503, detail="embedding service adapter not configured")
        vectors = await container.multimodal.embed(model=settings.embedding_model, inputs=payload.inputs)
        return {"vectors": vectors, "model": settings.embedding_model}

    @api.post("/v1/vision")
    async def vision(payload: VisionRequest) -> dict[str, Any]:
        if container.multimodal is None or not settings.vision_model:
            raise HTTPException(status_code=503, detail="vision service adapter not configured")
        if not payload.image_url.startswith(("https://", "data:image/")):
            raise HTTPException(status_code=422, detail="image_url must be HTTPS or a data image")
        content = await container.multimodal.vision(
            model=settings.vision_model, prompt=payload.prompt, image_url=payload.image_url
        )
        return {"content": content, "model": settings.vision_model}

    @api.post("/v1/audio/transcribe")
    async def transcribe(payload: TranscriptionRequest) -> dict[str, Any]:
        if container.multimodal is None or not settings.transcription_model:
            raise HTTPException(status_code=503, detail="STT service adapter not configured")
        try:
            audio = base64.b64decode(payload.audio_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalid base64 audio") from exc
        content = await container.multimodal.transcribe(
            model=settings.transcription_model, audio=audio, filename=payload.filename
        )
        return {"text": content, "model": settings.transcription_model}

    @api.post("/v1/audio/speech")
    async def speech(payload: SpeechRequest) -> dict[str, Any]:
        if container.multimodal is None or not settings.speech_model:
            raise HTTPException(status_code=503, detail="TTS service adapter not configured")
        audio_base64 = await container.multimodal.speech(
            model=settings.speech_model, voice=payload.voice, text=payload.text
        )
        return {"audio_base64": audio_base64, "model": settings.speech_model}

    @api.post("/v1/rerank")
    async def rerank(payload: RerankRequest) -> dict[str, Any]:
        if container.multimodal is None or not settings.rerank_model:
            raise HTTPException(status_code=503, detail="rerank service adapter not configured")
        scores = await container.multimodal.rerank(
            model=settings.rerank_model, query=payload.query, documents=payload.documents
        )
        return {"scores": scores, "model": settings.rerank_model}

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

    @api.post("/v1/agents/audit")
    def agent_audit(payload: AgentAuditRequest) -> dict[str, Any]:
        return container.agent_auditor.audit(
            payload.spec,
            tests_passed=payload.tests_passed,
            benchmark_passed=payload.benchmark_passed,
            independent_review_passed=payload.independent_review_passed,
            external_action_approved=payload.external_action_approved,
        ).model_dump()

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

    @api.post("/v1/evaluations/score")
    def evaluation_score(payload: EvalScoreRequest) -> dict[str, Any]:
        return container.evaluation.score(payload.case, payload.output).model_dump()

    @api.post("/v1/reviews")
    def review(payload: ReviewInput) -> dict[str, Any]:
        reports = container.reviews.review(payload)
        return {
            "approved": all(item.passed for item in reports),
            "reports": [item.model_dump() for item in reports],
        }

    @api.post("/v1/recovery/decide")
    def recovery(payload: RecoveryRequest) -> dict[str, Any]:
        return container.recovery.decide(payload.error_type, payload.status_code).model_dump()

    @api.get("/v1/improvements/{proposal_id}")
    def get_improvement(proposal_id: str) -> dict[str, Any]:
        proposal = container.improvements.get(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="improvement not found")
        return proposal.model_dump(mode="json")

    @api.post("/v1/improvements/advance")
    def advance_improvement(payload: ImprovementProposal) -> dict[str, Any]:
        try:
            return container.improvements.advance(payload).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/v1/improvements/{proposal_id}/reject")
    def reject_improvement(proposal_id: str) -> dict[str, Any]:
        try:
            return container.improvements.reject(proposal_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="improvement not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/v1/improvements/{proposal_id}/rollback")
    def rollback_improvement(proposal_id: str) -> dict[str, Any]:
        try:
            return container.improvements.rollback(proposal_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="improvement not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/v1/projects/validate")
    def validate_project(payload: ProjectRegistrationRequest) -> dict[str, Any]:
        contract = CANONICAL_PROJECTS.get(payload.key)
        if contract is None:
            raise HTTPException(status_code=404, detail="unknown canonical project")
        result = container.project_validator.validate_registration(contract, payload.registration)
        if payload.persist and result.valid:
            container.registry.upsert(RegistryKind.PROJECT, payload.key, payload.registration)
            container.audit.record(
                "project.registered",
                authenticated_actor("local-owner") or "local-owner",
                {"project": payload.key},
            )
        return result.model_dump()

    @api.get("/v1/world-state")
    def world_state() -> dict[str, Any]:
        return container.world_state.snapshot().model_dump(mode="json")

    @api.get("/v1/control-center")
    def control_center() -> dict[str, Any]:
        return container.control_center.snapshot().model_dump(mode="json")

    @api.get("/v1/telemetry/summary")
    def telemetry_summary() -> dict[str, Any]:
        return container.usage.summary()

    @api.get("/metrics")
    def metrics() -> Response:
        body, content_type = prometheus_payload()
        return Response(content=body, media_type=content_type)

    return api


app = create_app()
