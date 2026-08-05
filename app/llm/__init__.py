"""LLM 可插拔客户端层——工厂模式，所有提供者共享统一接口。"""

from app.llm.base import BaseLLMClient, BaseMultimodalClient
from app.llm.factory import create_multimodal_client, create_text_client

__all__ = [
    "BaseLLMClient",
    "BaseMultimodalClient",
    "create_text_client",
    "create_multimodal_client",
]
