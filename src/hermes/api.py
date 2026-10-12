from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from hermes.ai_core import AIService
from hermes.approval import ApprovalStatus, SqlApprovalStore
from hermes.auth import authenticated_actor
from hermes.architecture_policy import (
    PLATFORM_COMPONENT_DECISIONS,
    PYDANTIC_HARNESS_DECISIONS,
)
from hermes.authorization import build_policy_engine
from hermes.budget import BudgetGuard, BudgetPolicy
from hermes.cloud_sql import close_cloud_sql_resources
from hermes.cognitive import HybridIntentEngine, TaskGraphPlanner
from hermes.config import Settings, get_settings
from hermes.context import ContextCompactor, ContextItem, ContextRouter
from hermes.context_fabric import ContextFabric, ContextFragment
from hermes.contracts import DurableDispatcher
from hermes.control_center import ControlCenter
from hermes.decision import HypothesisEngine, ScenarioEngine, ScenarioOption
from hermes.domain import AgentSpec, ModelClass, ModelRouteRequest, PolicyRequest, TrustLevel
from hermes.durable import DBOSMissionDispatcher
from hermes.durable_benchmark import CANONICAL_SCENARIOS
from hermes.ecosystem import CANONICAL_PROJECTS, ProjectContractValidator
from hermes.event_store import SqlEventStore
from hermes.evaluation import EvalCase, EvaluationLab, ReviewInput, ReviewPanel
from hermes.evaluation_strategy import EvaluationPurpose, evaluation_route
from hermes.factories import AgentAuditor, AgentFactory, SkillFactory
from hermes.hardware import discover_hardware, recommend_local_runtime
from hermes.integrations import OpenAICompatibleGateway, ResearchClient, SecondBrainClient
from hermes.model_intelligence import AdaptiveModelRouter, PersistentModelIntelligence
from hermes.mcp_benchmark import MCPBenchmarkTarget, scenarios_for
from hermes.multimodal import OpenAICompatibleMultimodal
from hermes.operational_admission import OperationalAdmissionService
from hermes.operational_contracts import EventEnvelope, EventType, RequestModel, TaskStatus
from hermes.operational_persistence import SqlOperationalStore
from hermes.orchestrator import HermesOrchestrator
from hermes.persistence import Database, SqlAuditSink, SqlMissionStore
from hermes.privacy import SensitiveDataGuard
from hermes.project_registry import ProjectRegistration, ProjectRegistry
from hermes.readiness import ReadinessEvidence, evaluate_final_readiness
from hermes.recovery import FailureRecoveryEngine
from hermes.release_integrity import release_integrity
from hermes.registry import PersistentAgentRegistry, PersistentModelRegistry, SqlRegistry
from hermes.routing import ProjectRouter
from hermes.security import PromptInjectionDetector
from hermes.self_improvement import ImprovementProposal, PersistentImprovementEngine
from hermes.super_control import SuperControlPlane, build_super_router
from hermes.telemetry import SqlUsageStore, configure_tracing, prometheus_payload
from hermes.world_state import WorldStateBuilder


class MissionCreate(BaseModel):
    request: str = Field(min_length=1, max_length=20_000)


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


class ContextCompact(ContextSelect):
    max_chars: int = Field(default=32_000, ge=512, le=1_000_000)
    pinned_sources: set[str] = Field(default_factory=set)


class ContextAssemble(BaseModel):
    fragments: list[ContextFragment]
    target_project: str
    tenant: str = "owner"
    max_chars: int = Field(default=32_000, ge=512, le=1_000_000)
    pinned_sources: set[str] = Field(default_factory=set)


class FinalReadinessRequest(BaseModel):
    commit_sha: str = Field(min_length=7, max_length=64)
    evidence: list[ReadinessEvidence] = Field(default_factory=list)


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
        self.approvals = SqlApprovalStore(self.registry)
        self.models = PersistentModelRegistry(self.registry)
        self.agents = PersistentAgentRegistry(self.registry)
        self.usage = SqlUsageStore(self.db)
        self.budget = BudgetGuard(
            self.usage,
            self.registry,
            zero_cost_mode=settings.zero_cost_mode,
        )
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
            agent_provider=self.agents.load,
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
                budget=self.budget,
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
                application_version=settings.version,
                queue_name=settings.dbos_queue_name,
            )
            if settings.dbos_system_database_url
            else None
        )
        self.context = ContextRouter()
        self.compactor = ContextCompactor()
        self.context_fabric = ContextFabric(router=self.context, compactor=self.compactor)
        self.projects = ProjectRegistry(self.registry)
        self.operational_state = SqlOperationalStore(self.db)
        self.events = SqlEventStore(self.db)
        self.operational_admission = OperationalAdmissionService(
            state=self.operational_state,
            events=self.events,
            projects=self.projects,
            policy=self.policy,
        )
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

    def require_legacy_mission_api() -> None:
        if not settings.legacy_mission_api_active:
            raise HTTPException(
                status_code=410,
                detail="legacy mission API is disabled; use POST /requests",
            )

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "hermes-ai-platform"}

    @api.get("/ready")
    def ready() -> dict[str, str]:
        integrity = release_integrity(
            production=settings.is_production,
            version=settings.version,
            dependency_lock_sha256=settings.dependency_lock_sha256,
        )
        if not integrity.ready:
            raise HTTPException(
                status_code=503,
                detail={"reason": "release integrity blocked", "blockers": integrity.blockers},
            )
        with container.db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}

    @api.post("/requests")
    def create_request(payload: RequestModel) -> dict[str, Any]:
        actor = authenticated_actor("local-owner") or "local-owner"
        try:
            result = container.operational_admission.admit(payload, actor=actor)
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    @api.get("/requests/{request_id}")
    def get_request(request_id: str) -> dict[str, Any]:
        request = container.operational_state.get_request(request_id)
        if request is None:
            raise HTTPException(status_code=404, detail="request not found")
        return request.model_dump(mode="json")

    @api.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        task = container.operational_state.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return task.model_dump(mode="json")

    @api.post("/tasks/{task_id}/cancel")
    def cancel_task(task_id: str) -> dict[str, Any]:
        task = container.operational_state.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        if task.status == TaskStatus.COMPLETED:
            raise HTTPException(status_code=409, detail="completed task cannot be cancelled")
        if task.status != TaskStatus.CANCELLED:
            cancelled = task.model_copy(
                update={
                    "status": TaskStatus.CANCELLED,
                    "finished_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            )
            container.operational_state.save_task(cancelled)
        else:
            cancelled = task

        event_id = "event-" + hashlib.sha256(
            f"{task_id}|TASK_CANCELLED".encode()
        ).hexdigest()[:32]
        if container.events.get(event_id) is None:
            request = container.operational_state.get_request(cancelled.request_id)
            correlation_id = request.correlation_id if request is not None else cancelled.request_id
            container.events.append(
                EventEnvelope(
                    event_id=event_id,
                    event_type=EventType.TASK_CANCELLED,
                    producer="hermes-api",
                    project_id=cancelled.project_id,
                    correlation_id=correlation_id,
                    causation_id=cancelled.task_id,
                    payload={
                        "task_id": cancelled.task_id,
                        "workflow_id": cancelled.workflow_id,
                        "status": cancelled.status.value,
                    },
                )
            )
        return cancelled.model_dump(mode="json")

    @api.get("/workflows/{workflow_id}")
    def get_workflow(workflow_id: str) -> dict[str, Any]:
        workflow = container.operational_state.get_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return {
            "workflow": workflow.model_dump(mode="json"),
            "tasks": [
                item.model_dump(mode="json")
                for item in container.operational_state.tasks_for_workflow(workflow_id)
            ],
        }

    @api.get("/agents")
    def operational_agents() -> list[dict[str, Any]]:
        return [agent.model_dump(mode="json") for agent in container.agents.load()]

    @api.get("/services")
    def operational_services() -> list[dict[str, Any]]:
        return [project.model_dump(mode="json") for project in container.projects.list()]

    @api.get("/v1/release/readiness")
    def release_readiness() -> dict[str, Any]:
        return release_integrity(
            production=settings.is_production,
            version=settings.version,
            dependency_lock_sha256=settings.dependency_lock_sha256,
        ).model_dump(mode="json")

    @api.post("/v1/final-readiness/evaluate")
    def final_readiness(payload: FinalReadinessRequest) -> dict[str, Any]:
        return evaluate_final_readiness(
            commit_sha=payload.commit_sha,
            evidence=payload.evidence,
        ).model_dump(mode="json")

    @api.get("/v1/capabilities")
    def capabilities() -> dict[str, Any]:
        return {
            "capabilities": [
                "mission_planning",
                "model_routing",
                "adaptive_model_routing",
                "model_performance_learning",
                "context_routing",
                "context_compaction",
                "context_fabric",
                "capability_autonomy",
                "project_registry",
                "final_readiness_gate",
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
                "persistent_tool_approval",
                "multi_window_spend_limits",
                "cache_efficiency_monitoring",
                "release_integrity_gate",
                "sandbox_coder_contract",
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

    @api.post("/v1/budgets")
    def save_budget(payload: BudgetPolicy) -> dict[str, Any]:
        container.budget.save(payload)
        actor = authenticated_actor("local-owner") or "local-owner"
        container.audit.record(
            "budget.saved",
            actor,
            {
                "project": payload.project,
                "max_daily_usd": payload.max_daily_usd,
                "max_weekly_usd": payload.max_weekly_usd,
                "max_monthly_usd": payload.max_monthly_usd,
            },
        )
        return payload.model_dump(mode="json")

    @api.get("/v1/budgets")
    def get_budget(project: str | None = None) -> dict[str, Any]:
        policy = container.budget.policy(project)
        if policy is None:
            raise HTTPException(status_code=404, detail="budget policy not found")
        return policy.model_dump(mode="json")

    @api.get("/v1/approvals")
    def list_approvals(status: ApprovalStatus | None = None) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in container.approvals.list(status=status)
        ]

    @api.get("/v1/approvals/{approval_id}")
    def get_approval(approval_id: str) -> dict[str, Any]:
        record = container.approvals.get(approval_id)
        if record is None:
            raise HTTPException(status_code=404, detail="approval not found")
        return record.model_dump(mode="json")

    @api.post("/v1/approvals/{approval_id}/approve")
    def approve_action(approval_id: str) -> dict[str, Any]:
        approver = authenticated_actor("local-owner") or "local-owner"
        try:
            record = container.approvals.approve(approval_id, approver=approver)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="approval not found") from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        container.audit.record(
            "approval.approved",
            approver,
            {"approval_id": approval_id, "action": record.action, "resource": record.resource},
        )
        return record.model_dump(mode="json")

    @api.post("/v1/approvals/{approval_id}/reject")
    def reject_action(approval_id: str) -> dict[str, Any]:
        approver = authenticated_actor("local-owner") or "local-owner"
        try:
            record = container.approvals.reject(approval_id, approver=approver)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="approval not found") from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        container.audit.record(
            "approval.rejected",
            approver,
            {"approval_id": approval_id, "action": record.action, "resource": record.resource},
        )
        return record.model_dump(mode="json")

    @api.post("/v1/missions")
    async def create_mission(payload: MissionCreate) -> dict[str, Any]:
        require_legacy_mission_api()
        actor = authenticated_actor("local-owner") or "local-owner"
        mission = await container.orchestrator.create_mission(payload.request, actor=actor)
        return mission.model_dump(mode="json")

    @api.get("/v1/missions/{mission_id}")
    def get_mission(mission_id: str) -> dict[str, Any]:
        require_legacy_mission_api()
        mission = container.mission_store.get(mission_id)
        if mission is None:
            raise HTTPException(status_code=404, detail="mission not found")
        return mission.model_dump(mode="json")

    @api.post("/v1/missions/{mission_id}/dispatch")
    def dispatch_mission(mission_id: str) -> dict[str, str]:
        require_legacy_mission_api()
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
        actor = authenticated_actor("local-owner") or "local-owner"
        request = payload.model_copy(update={"actor": actor, "subject": actor})
        return container.policy.authorize(request).model_dump()

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

    @api.post("/v1/context/compact")
    def context_compact(payload: ContextCompact) -> dict[str, Any]:
        selected = container.context.select(
            payload.items,
            target_project=payload.target_project,
            tenant=payload.tenant,
        )
        result = container.compactor.compact(
            selected,
            max_chars=payload.max_chars,
            pinned_sources=payload.pinned_sources,
        )
        return result.model_dump(mode="json")

    @api.post("/v1/context/assemble")
    def context_assemble(payload: ContextAssemble) -> dict[str, Any]:
        result = container.context_fabric.assemble(
            payload.fragments,
            target_project=payload.target_project,
            tenant=payload.tenant,
            max_chars=payload.max_chars,
            pinned_sources=payload.pinned_sources,
        )
        return result.model_dump(mode="json")

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
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/v1/improvements/{proposal_id}/reject")
    def reject_improvement(proposal_id: str) -> dict[str, Any]:
        try:
            return container.improvements.reject(proposal_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="improvement not found") from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/v1/improvements/{proposal_id}/rollback")
    def rollback_improvement(proposal_id: str) -> dict[str, Any]:
        try:
            return container.improvements.rollback(proposal_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="improvement not found") from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/v1/projects/validate")
    def validate_project(payload: ProjectRegistrationRequest) -> dict[str, Any]:
        contract = CANONICAL_PROJECTS.get(payload.key)
        if contract is None:
            raise HTTPException(status_code=404, detail="unknown canonical project")
        result = container.project_validator.validate_registration(contract, payload.registration)
        if payload.persist and result.valid:
            registration = ProjectRegistration(
                key=payload.key,
                **payload.registration,
            )
            container.projects.save(registration)
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

    @api.get("/v1/telemetry/cache-efficiency")
    def cache_efficiency(
        project: str | None = None,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        return container.usage.cache_efficiency(
            project=project,
            model_id=model_id,
        ).model_dump(mode="json")

    @api.get("/metrics")
    def metrics() -> Response:
        body, content_type = prometheus_payload()
        return Response(content=body, media_type=content_type)

    return api


app = create_app()
