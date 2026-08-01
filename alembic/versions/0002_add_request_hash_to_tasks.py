"""add request_hash to tasks for idempotency

Revision ID: 0002_request_hash
Revises: ebde5c0c9d43
Create Date: 2026-07-23 22:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002_request_hash'
down_revision: Union[str, Sequence[str], None] = 'ebde5c0c9d43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("request_hash", sa.String(32), nullable=True))
    op.create_index("ix_tasks_request_hash", "tasks", ["request_hash"])


def downgrade() -> None:
    op.drop_index("ix_tasks_request_hash", "tasks")
    op.drop_column("tasks", "request_hash")
