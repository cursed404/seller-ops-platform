"""Начальная схема

Revision ID: 0001_initial
Revises:
Create Date: 2025-10-14 03:30:00
"""

from collections.abc import Sequence

from alembic import op

from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.base import Base

revision = "0001_initial"
down_revision = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
