"""initial Hermes operational schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hermes_missions",
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("mission_id"),
    )
    op.create_index("ix_hermes_missions_status", "hermes_missions", ["status"])
    op.create_index("ix_hermes_missions_updated_at", "hermes_missions", ["updated_at"])

    op.create_table(
        "hermes_audit_events",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_hermes_audit_events_event_type", "hermes_audit_events", ["event_type"])
    op.create_index("ix_hermes_audit_events_actor", "hermes_audit_events", ["actor"])

    op.create_table(
        "hermes_registry",
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("item_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("kind", "item_id"),
    )
    op.create_index("ix_hermes_registry_status", "hermes_registry", ["status"])
    op.create_index("ix_hermes_registry_updated_at", "hermes_registry", ["updated_at"])

    op.create_table(
        "hermes_usage_events",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=True),
        sa.Column("project", sa.String(length=120), nullable=True),
        sa.Column("agent", sa.String(length=120), nullable=True),
        sa.Column("model_id", sa.String(length=160), nullable=True),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    for column in (
        "mission_id",
        "project",
        "agent",
        "model_id",
        "provider",
        "operation",
        "success",
        "error_type",
        "created_at",
    ):
        op.create_index(f"ix_hermes_usage_events_{column}", "hermes_usage_events", [column])


def downgrade() -> None:
    op.drop_table("hermes_usage_events")
    op.drop_table("hermes_registry")
    op.drop_table("hermes_audit_events")
    op.drop_table("hermes_missions")
