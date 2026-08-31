"""产品分析请求模型"""

from typing import Optional

from pydantic import BaseModel, Field


class AnalysisSubmitRequest(BaseModel):
    name: str = Field(min_length=1)
    function: str = Field(min_length=1)
    price: str = Field(min_length=1)
    extra: str = ""
    custom_prompt: str = ""
    model: str = ""  # 多模态 provider：gpt / doubao / kimi，空用 .env


class StrategyRequest(BaseModel):
    analysis: str = Field(min_length=1)
    system_prompt: str = ""
    model: str = ""  # DeepSeek 模型名：deepseek-v4-pro / deepseek-v4-flash，空用 .env
    parent_task_id: Optional[str] = None

