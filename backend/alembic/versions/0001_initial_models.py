"""initial models migration

Revision ID: 0001_initial_models
Revises:
Create Date: 2026-04-28 02:00:00
"""

from __future__ import annotations

from alembic import op

from app.core.database import Base
from app.core.schemas import (  # noqa: F401
    ChatMessageORM,
    ComplianceResultORM,
    IntentResultORM,
    LeadProfileORM,
    MarketSnapshotORM,
    ScoreResultORM,
)


# revision identifiers, used by Alembic.
revision = "0001_initial_models"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
