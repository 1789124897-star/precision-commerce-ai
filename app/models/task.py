"""Task 模型"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TASK_TYPE_SCRAPE = "scrape"
TASK_TYPE_ANALYSIS = "analysis"
TASK_TYPE_STRATEGY = "strategy"
TASK_TYPE_IMAGE_GEN = "image_gen"
TASK_TYPE_SCRIPT_GEN = "script_gen"
TASK_TYPE_TTS = "tts"
TASK_TYPE_VIDEO_COMPOSE = "video_compose"
TASK_TYPE_SHOT_GEN = "shot_gen"

TASK_TYPES = [
    TASK_TYPE_SCRAPE,
    TASK_TYPE_ANALYSIS,
    TASK_TYPE_STRATEGY,
    TASK_TYPE_IMAGE_GEN,
    TASK_TYPE_SCRIPT_GEN,
    TASK_TYPE_TTS,
    TASK_TYPE_VIDEO_COMPOSE,
    TASK_TYPE_SHOT_GEN,
]

STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILURE = "FAILURE"
STATUS_NOT_FOUND = "NOT_FOUND"

TASK_STATUSES = [STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCESS, STATUS_FAILURE]


def gen_task_id() -> str:
    
    return uuid.uuid4().hex 


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True, default=gen_task_id)
    parent_task_id: Mapped[Optional[str]] = mapped_column(String(32), default=None, index=True)
    celery_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_PENDING)
    request_json: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    request_hash: Mapped[Optional[str]] = mapped_column(String(32), default=None, index=True)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, default=None)
    error_message: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
