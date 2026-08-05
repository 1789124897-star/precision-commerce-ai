"""LLM 抽象基类"""

from abc import ABC, abstractmethod
from typing import Any


class BaseLLMClient(ABC):
    """纯文本 LLM 客户端"""

    @abstractmethod
    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        """发送提示词，返回已解析的 JSON dict。"""
        ...


class BaseMultimodalClient(ABC):
    """多模态客户端"""

    @abstractmethod
    async def analyze_multimodal(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: list[str],
    ) -> str:
        """传入图片 data URL + 提示词，返回分析文本。"""
        ...
