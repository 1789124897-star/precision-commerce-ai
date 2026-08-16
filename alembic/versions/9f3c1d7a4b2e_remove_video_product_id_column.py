"""remove video product_id column

Revision ID: 9f3c1d7a4b2e
Revises: 55cf93dc8485
Create Date: 2026-08-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9f3c1d7a4b2e'
down_revision: Union[str, Sequence[str], None] = '55cf93dc8485'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_videos_product_id", table_name="videos")
    op.drop_column('videos', 'product_id')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('videos', sa.Column('product_id', sa.String(32), nullable=True, server_default=''))
    op.create_index("ix_videos_product_id", "videos", ["product_id"])
