import asyncio
from pathlib import Path

from hermes.ai_core import AIService
from hermes.domain import ModelClass, ModelProfile, ModelRouteRequest
from hermes.model_intelligence import AdaptiveModelRouter, PersistentModelIntelligence
from hermes.persistence import Database
from hermes.privacy import SensitiveDataGuard
from hermes.telemetry import SqlUsageStore


class CaptureGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def complete(self, *, model: str, system: str, user: str) -> str:
        self.calls.append((model, system, user))
        return f"ok:{model}"


def make_db(tmp_path: Path, name: str) -> Database:
    db = Database(f"sqlite:///{tmp_path / name}")
    db.create_schema()
    return db


def make_profile(model_id: str, *, local: bool, quality: float) -> ModelProfile:
    return ModelProfile(
        model_id=model_id,
        provider="local" if local else "cloud",
        model=model_id,
        classes={ModelClass.REASONING},
        local=local,
        quality_score=quality,
        latency_score=0.5,
        cost_score=0.5,
        benchmark_score=quality,
    )


def test_secret_skips_external_and_falls_back_to_local(tmp_path: Path) -> None:
    db = make_db(tmp_path, "secret.db")
    intelligence = PersistentModelIntelligence(db)
    router = AdaptiveModelRouter(
        [make_profile("cloud", local=False, quality=1.0), make_profile("local", local=True, quality=0.7)],
        intelligence,
    )
    gateway = CaptureGateway()
    service = AIService(
        gateway=gateway,
        router=router,
        usage=SqlUsageStore(db),
        privacy=SensitiveDataGuard(),
        intelligence=intelligence,
    )
    result = asyncio.run(
        service.generate(
            request=ModelRouteRequest(required_classes={ModelClass.REASONING}),
            system="safe",
            user="Authorization: Bearer abcdefghijklmnopqrst",
        )
    )
    assert result.route.model_id == "local"
    assert result.attempts == 2
    assert gateway.calls == [("local", "safe", "Authorization: Bearer abcdefghijklmnopqrst")]
    cloud = intelligence.summarize("cloud", ModelClass.REASONING)
    local = intelligence.summarize("local", ModelClass.REASONING)
    assert cloud.samples == 1 and cloud.success_rate == 0.0
    assert local.samples == 1 and local.success_rate == 1.0


def test_personal_data_is_redacted_for_external_model(tmp_path: Path) -> None:
    db = make_db(tmp_path, "pii.db")
    intelligence = PersistentModelIntelligence(db)
    router = AdaptiveModelRouter([make_profile("cloud", local=False, quality=1.0)], intelligence)
    gateway = CaptureGateway()
    service = AIService(
        gateway=gateway,
        router=router,
        usage=SqlUsageStore(db),
        privacy=SensitiveDataGuard(),
        intelligence=intelligence,
    )
    result = asyncio.run(
        service.generate(
            request=ModelRouteRequest(required_classes={ModelClass.REASONING}),
            system="safe",
            user="contato user@example.com",
        )
    )
    assert result.route.model_id == "cloud"
    assert "user@example.com" not in gateway.calls[0][2]
    assert "[REDACTED:email]" in gateway.calls[0][2]
    assert intelligence.summarize("cloud", ModelClass.REASONING).samples == 1
