"""durable event store outbox and dead-letter queue

Revision ID: 0005_event_outbox_dlq
Revises: 0004_operational_state
Create Date: 2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_event_outbox_dlq"
down_revision: str | None = "0004_operational_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "hermes_events",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("producer", sa.String(length=160), nullable=False),
        sa.Column("project_id", sa.String(length=120), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("causation_id", sa.String(length=128), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("envelope", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    _indexes(
        "hermes_events",
        (
            "event_type",
            "producer",
            "project_id",
            "schema_version",
            "correlation_id",
            "causation_id",
            "created_at",
        ),
    )

    op.create_table(
        "hermes_event_outbox",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    _indexes(
        "hermes_event_outbox",
        ("status", "next_attempt_at", "created_at", "updated_at"),
    )

    op.create_table(
        "hermes_dead_letters",
        sa.Column("dlq_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("project_id", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_action", sa.String(length=160), nullable=False),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("dlq_id"),
        sa.UniqueConstraint("event_id", name="uq_hermes_dead_letters_event"),
    )
    _indexes(
        "hermes_dead_letters",
        ("event_id", "event_type", "project_id", "failed_at", "replayed_at"),
    )


def downgrade() -> None:
    op.drop_table("hermes_dead_letters")
    op.drop_table("hermes_event_outbox")
    op.drop_table("hermes_events")
