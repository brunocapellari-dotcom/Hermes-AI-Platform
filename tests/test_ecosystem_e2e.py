from datetime import UTC, datetime

from contracts.ecosystem_e2e import (
    EcosystemSnapshot,
    EvidenceKind,
    EvidenceRef,
    ServiceHealth,
    ServiceState,
)


def evidence(kind: EvidenceKind, passed: bool = True) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        uri=f"https://evidence.local/{kind.value}",
        observed_at=datetime.now(UTC),
        passed=passed,
    )


def test_service_requires_all_core_evidence_to_be_promotable() -> None:
    service = ServiceHealth(
        service_id="research-ai",
        version="1.0.0",
        state=ServiceState.HEALTHY,
        checked_at=datetime.now(UTC),
        evidence=[
            evidence(EvidenceKind.CI),
            evidence(EvidenceKind.HEALTH),
            evidence(EvidenceKind.READINESS),
        ],
    )
    assert service.promotable is False


def test_service_is_promotable_only_with_complete_passing_evidence() -> None:
    service = ServiceHealth(
        service_id="hermes-ai",
        version="1.0.0",
        state=ServiceState.HEALTHY,
        checked_at=datetime.now(UTC),
        evidence=[
            evidence(EvidenceKind.CI),
            evidence(EvidenceKind.HEALTH),
            evidence(EvidenceKind.READINESS),
            evidence(EvidenceKind.E2E),
        ],
    )
    snapshot = EcosystemSnapshot(
        generated_at=datetime.now(UTC),
        services=[service],
    )
    assert service.promotable is True
    assert snapshot.promotable_services() == {"hermes-ai"}


def test_failed_e2e_blocks_promotion() -> None:
    service = ServiceHealth(
        service_id="second-brain",
        version="1.0.0",
        state=ServiceState.HEALTHY,
        checked_at=datetime.now(UTC),
        evidence=[
            evidence(EvidenceKind.CI),
            evidence(EvidenceKind.HEALTH),
            evidence(EvidenceKind.READINESS),
            evidence(EvidenceKind.E2E, passed=False),
        ],
    )
    assert service.promotable is False
