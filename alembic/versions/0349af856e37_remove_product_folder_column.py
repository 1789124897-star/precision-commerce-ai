"""remove_product_folder_column

Revision ID: 0349af856e37
Revises: 0002_request_hash
Create Date: 2026-08-02 20:09:08.929823

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '0349af856e37'
down_revision: Union[str, Sequence[str], None] = '0002_request_hash'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('products', 'folder')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('products', sa.Column('folder', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=2048), nullable=False, server_default=sa.text("''")))
