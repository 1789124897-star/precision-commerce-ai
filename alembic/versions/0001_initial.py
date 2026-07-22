"""init

Revision ID: 0001_initial
Revises: 
Create Date: 2026-07-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── products ──
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(32), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("folder", sa.String(500), nullable=False, server_default=""),
        sa.Column("image_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_products_task_id", "products", ["task_id"])

    # ── tasks ──
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(32), nullable=False),
        sa.Column("parent_task_id", sa.String(32), nullable=True),
        sa.Column("celery_id", sa.String(64), nullable=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("request_json", mysql.JSON(), nullable=True),
        sa.Column("result_json", mysql.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_tasks_task_id", "tasks", ["task_id"])
    op.create_index("ix_tasks_parent_task_id", "tasks", ["parent_task_id"])

    # ── analyses ──
    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(32), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("product_function", sa.String(500), nullable=False, server_default=""),
        sa.Column("price_range", sa.String(100), nullable=False, server_default=""),
        sa.Column("extra_info", sa.String(1000), nullable=False, server_default=""),
        sa.Column("image_paths", sa.Text(), nullable=False, server_default=""),
        sa.Column("result_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_analyses_task_id", "analyses", ["task_id"])

    # ── strategies ──
    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(32), nullable=False),
        sa.Column("analysis_task_id", sa.String(32), nullable=True),
        sa.Column("strategy_type", sa.String(50), nullable=False),
        sa.Column("result_text", mysql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "strategy_type", name="uq_task_strategy"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_strategies_task_id", "strategies", ["task_id"])
    op.create_index("ix_strategies_analysis_task_id", "strategies", ["analysis_task_id"])

    # ── videos ──
    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(32), nullable=False),
        sa.Column("product_id", sa.String(32), nullable=True, server_default=""),
        sa.Column("video_type", sa.String(20), nullable=False),
        sa.Column("source_images", sa.Text(), nullable=False, server_default=""),
        sa.Column("audio_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("srt_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("output_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("duration_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("resolution", sa.String(10), nullable=False, server_default=""),
        sa.Column("aspect_ratio", sa.String(10), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="generated"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_videos_task_id", "videos", ["task_id"])
    op.create_index("ix_videos_product_id", "videos", ["product_id"])


def downgrade() -> None:
    op.drop_table("videos")
    op.drop_table("strategies")
    op.drop_table("analyses")
    op.drop_table("tasks")
    op.drop_table("products")
