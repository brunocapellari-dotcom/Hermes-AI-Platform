"""canonical request workflow task and checkpoint persistence

Revision ID: 0004_operational_state
Revises: 0003_cached_input_tokens
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_operational_state"
down_revision: str | None = "0003_cached_input_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "hermes_requests",
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("source_project", sa.String(length=120), nullable=False),
        sa.Column("source_agent", sa.String(length=160), nullable=True),
        sa.Column("requested_capability", sa.String(length=160), nullable=False),
        sa.Column("priority", sa.String(length=4), nullable=False),
        sa.Column("security_level", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("request_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_hermes_requests_tenant_idempotency",
        ),
    )
    _indexes(
        "hermes_requests",
        (
            "source_project",
            "source_agent",
            "requested_capability",
            "priority",
            "security_level",
            "correlation_id",
            "tenant_id",
            "created_at",
        ),
    )

    op.create_table(
        "hermes_workflows",
        sa.Column("workflow_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("workflow_type", sa.String(length=160), nullable=False),
        sa.Column("workflow_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=4), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("workflow_id"),
    )
    _indexes(
        "hermes_workflows",
        ("request_id", "workflow_type", "status", "priority", "created_at", "updated_at"),
    )

    op.create_table(
        "hermes_tasks",
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("workflow_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=120), nullable=False),
        sa.Column("agent_id", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=4), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_hermes_tasks_project_idempotency",
        ),
    )
    _indexes(
        "hermes_tasks",
        (
            "request_id",
            "workflow_id",
            "project_id",
            "agent_id",
            "status",
            "priority",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ),
    )

    op.create_table(
        "hermes_checkpoints",
        sa.Column("checkpoint_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workflow_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("stage", sa.String(length=160), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("checkpoint_id"),
    )
    _indexes(
        "hermes_checkpoints",
        ("workflow_id", "task_id", "stage", "created_at"),
    )


def downgrade() -> None:
    op.drop_table("hermes_checkpoints")
    op.drop_table("hermes_tasks")
    op.drop_table("hermes_workflows")
    op.drop_table("hermes_requests")
