from abc import ABC, abstractmethod
from typing import Any


class BaseLLMClient(ABC):

    @abstractmethod
    async def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 8192,
    ) -> str:
        """发送 system + user 提示词，返回模型原始文本响应。"""
        ...

    @abstractmethod
    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        """发送 system + user 提示词，要求模型返回 JSON 并反序列化为 dict。"""
        ...

    @abstractmethod
    async def analyze_multimodal(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: list[str],
    ) -> str:
        """传入图片 data URL 和文本提示词，返回模型对图片的分析结果。"""
        ...
