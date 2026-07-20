"""分析 & 策略模型"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_function: Mapped[str] = mapped_column(String(500), default="")
    price_range: Mapped[str] = mapped_column(String(100), default="")
    extra_info: Mapped[str] = mapped_column(String(1000), default="")
    image_paths: Mapped[str] = mapped_column(Text, default="")
    result_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Strategy(Base):
    __tablename__ = "strategies"
    __table_args__ = (
        UniqueConstraint("task_id", "strategy_type", name="uq_task_strategy"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    analysis_task_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    result_text: Mapped[dict] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
