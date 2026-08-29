"""LLM 客户端工厂"""

from app.core.config import settings
from app.llm.base import BaseImageClient, BaseLLMClient, BaseMultimodalClient


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

    if provider == "gpt":
        from app.llm.gpt_client import GptClient
        return GptClient()

    raise ValueError(f"不支持的 MULTIMODAL_PROVIDER: {provider}，可选: doubao / kimi / gpt")


def create_image_client(model: str) -> BaseImageClient:
    """按模型名选择生图客户端：gpt- 前缀走 GPT，其余走 Seedream。"""
    if model.startswith("gpt-"):
        from app.llm.gpt_image_client import GptImageClient
        return GptImageClient(model=model)

    from app.llm.seedream_image_client import SeedreamImageClient
    return SeedreamImageClient(model=model)
