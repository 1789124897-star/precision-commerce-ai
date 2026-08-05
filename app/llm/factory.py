"""LLM 客户端工厂"""

from app.core.config import settings
from app.llm.base import BaseLLMClient, BaseMultimodalClient


def create_text_client() -> BaseLLMClient:
    """纯文本推理客户端"""
    provider = settings.TEXT_PROVIDER

    if provider == "deepseek":
        from app.llm.deepseek_client import DeepSeekClient
        return DeepSeekClient()

    raise ValueError(f"不支持的 TEXT_PROVIDER: {provider}，可选: deepseek")


def create_multimodal_client() -> BaseMultimodalClient:
    """多模态分析客户端"""
    provider = settings.MULTIMODAL_PROVIDER

    if provider == "doubao":
        from app.llm.doubao_client import DoubaoClient
        return DoubaoClient()

    if provider == "kimi":
        from app.llm.kimi_client import KimiClient
        return KimiClient()

    raise ValueError(f"不支持的 MULTIMODAL_PROVIDER: {provider}，可选: doubao / kimi")
