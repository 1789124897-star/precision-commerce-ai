"""Task 模型"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TASK_TYPES = ["scrape", "analysis", "strategy", "image_gen", "script_gen", "tts", "video_compose", "shot_gen"]
TASK_STATUSES = ["PENDING", "RUNNING", "SUCCESS", "FAILURE"]


def gen_task_id() -> str:
    """生成 32 位 UUID，供 Service 层调用。"""
    return uuid.uuid4().hex


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True, default=gen_task_id)
    parent_task_id: Mapped[Optional[str]] = mapped_column(String(32), default=None, index=True)
    celery_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    request_json: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    error_message: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
