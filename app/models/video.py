"""视频模型"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(32), nullable=True, index=True, default="")
    video_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_images: Mapped[str] = mapped_column(Text, default="")
    audio_path: Mapped[str] = mapped_column(String(500), default="")
    srt_path: Mapped[str] = mapped_column(String(500), default="")
    output_path: Mapped[str] = mapped_column(String(500), default="")
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    resolution: Mapped[str] = mapped_column(String(10), default="")
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="")
    status: Mapped[str] = mapped_column(String(20), default="generated")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
