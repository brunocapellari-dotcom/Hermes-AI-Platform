from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_model_performance"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hermes_model_performance",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_id", sa.String(length=160), nullable=False),
        sa.Column("task_class", sa.String(length=80), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("quality", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_hermes_model_performance_model_id", "hermes_model_performance", ["model_id"])
    op.create_index("ix_hermes_model_performance_task_class", "hermes_model_performance", ["task_class"])
    op.create_index("ix_hermes_model_performance_success", "hermes_model_performance", ["success"])
    op.create_index("ix_hermes_model_performance_observed_at", "hermes_model_performance", ["observed_at"])


def downgrade() -> None:
    op.drop_index("ix_hermes_model_performance_observed_at", table_name="hermes_model_performance")
    op.drop_index("ix_hermes_model_performance_success", table_name="hermes_model_performance")
    op.drop_index("ix_hermes_model_performance_task_class", table_name="hermes_model_performance")
    op.drop_index("ix_hermes_model_performance_model_id", table_name="hermes_model_performance")
    op.drop_table("hermes_model_performance")
