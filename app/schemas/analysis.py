"""产品分析请求模型"""
from typing import Optional

from pydantic import BaseModel, Field


class AnalysisSubmitRequest(BaseModel):
    name: str = Field(min_length=1)
    function: str = Field(min_length=1)
    price: str = Field(min_length=1)
    extra: str = ""
    custom_prompt: str = ""


class StrategyRequest(BaseModel):
    analysis: str = Field(min_length=1)
    system_prompt: str = ""
    parent_task_id: Optional[str] = None

