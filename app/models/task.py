"""Task 模型"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TASK_TYPES = ["scrape", "analysis", "strategy", "image_gen", "script_gen", "tts", "video_compose", "shot_gen"]
TASK_STATUSES = ["PENDING", "RUNNING", "SUCCESS", "FAILURE"]


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    parent_task_id: Mapped[str | None] = mapped_column(String(32), default=None, index=True)
    celery_id: Mapped[str | None] = mapped_column(String(64), default=None)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    request_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    result_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
