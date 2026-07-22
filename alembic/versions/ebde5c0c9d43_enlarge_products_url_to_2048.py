"""enlarge products.url to 2048

Revision ID: ebde5c0c9d43
Revises: 0001_initial
Create Date: 2026-07-23 03:28:34.164197

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ebde5c0c9d43'
down_revision: Union[str, Sequence[str], None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("products", "url", existing_type=sa.String(500), type_=sa.String(2048), nullable=False)


def downgrade() -> None:
    op.alter_column("products", "url", existing_type=sa.String(2048), type_=sa.String(500), nullable=False)
