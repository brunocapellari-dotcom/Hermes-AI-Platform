from datetime import UTC, datetime

from hermes.domain import ModelClass
from hermes.model_intelligence import ModelPerformanceSample, PersistentModelIntelligence
from hermes.persistence import Database


def test_model_intelligence_persists_and_rehydrates() -> None:
    db = Database("sqlite:///:memory:")
    db.create_schema()
    first = PersistentModelIntelligence(db)
    first.record(
        ModelPerformanceSample(
            model_id="persistent-model",
            task_class=ModelClass.REASONING,
            success=True,
            quality=0.9,
            latency_ms=250,
            cost_usd=0.001,
            observed_at=datetime.now(UTC),
        )
    )
    second = PersistentModelIntelligence(db)
    summary = second.summarize("persistent-model", ModelClass.REASONING)
    assert summary.samples == 1
    assert summary.success_rate == 1.0
    assert summary.quality_score == 0.9
