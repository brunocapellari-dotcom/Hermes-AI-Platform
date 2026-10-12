"""operational task leases and priority scheduling

Revision ID: 0006_operational_task_leases
Revises: 0005_event_outbox_dlq
Create Date: 2026-10-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_operational_task_leases"
down_revision: str | None = "0005_event_outbox_dlq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hermes_task_leases",
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(length=160), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index("ix_hermes_task_leases_available_at", "hermes_task_leases", ["available_at"])
    op.create_index("ix_hermes_task_leases_lease_owner", "hermes_task_leases", ["lease_owner"])
    op.create_index("ix_hermes_task_leases_lease_until", "hermes_task_leases", ["lease_until"])
    op.create_index("ix_hermes_task_leases_heartbeat_at", "hermes_task_leases", ["heartbeat_at"])
    op.create_index("ix_hermes_task_leases_updated_at", "hermes_task_leases", ["updated_at"])


def downgrade() -> None:
    op.drop_table("hermes_task_leases")
