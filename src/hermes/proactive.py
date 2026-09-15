from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from hermes.world_state import WorldState


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class IntelligenceAlert(BaseModel):
    code: str
    severity: AlertSeverity
    message: str
    recommended_action: str


class DailyIntelligence(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    alerts: list[IntelligenceAlert]
    requires_owner_attention: bool


class DailyIntelligenceBuilder:
    """Read-only proactive intelligence; it never performs the recommended action."""

    def build(self, state: WorldState) -> DailyIntelligence:
        alerts: list[IntelligenceAlert] = []
        failures = int(state.usage.get("failures", 0))
        blocked = int(state.mission_status.get("blocked", 0))
        failed = int(state.mission_status.get("failed", 0))
        if failed:
            alerts.append(
                IntelligenceAlert(
                    code="MISSION_FAILURES",
                    severity=AlertSeverity.CRITICAL,
                    message=f"{failed} mission(s) failed",
                    recommended_action="inspect mission checkpoints and recovery decisions",
                )
            )
        if blocked:
            alerts.append(
                IntelligenceAlert(
                    code="BLOCKED_MISSIONS",
                    severity=AlertSeverity.WARNING,
                    message=f"{blocked} mission(s) blocked",
                    recommended_action="review policy, missing adapter, or owner approval requirement",
                )
            )
        if failures:
            alerts.append(
                IntelligenceAlert(
                    code="USAGE_FAILURES",
                    severity=AlertSeverity.WARNING,
                    message=f"{failures} tracked operation(s) failed",
                    recommended_action="review provider and tool reliability before expansion",
                )
            )
        if not state.registry_counts.get("project", 0):
            alerts.append(
                IntelligenceAlert(
                    code="NO_PROJECTS",
                    severity=AlertSeverity.INFO,
                    message="no project adapters are registered",
                    recommended_action="register validated project contracts before live orchestration",
                )
            )
        attention = any(alert.severity != AlertSeverity.INFO for alert in alerts)
        return DailyIntelligence(alerts=alerts, requires_owner_attention=attention)
