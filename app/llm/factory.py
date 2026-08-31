"""LLM 客户端工厂"""

from app.core.config import settings
from app.llm.base import BaseImageClient, BaseLLMClient, BaseMultimodalClient


def create_text_client(model: str = "") -> BaseLLMClient:
    """纯文本推理客户端。"""
    provider = settings.TEXT_PROVIDER

    if provider == "deepseek":
        from app.llm.deepseek_client import DeepSeekClient
        return DeepSeekClient(model=model)

    raise ValueError(f"不支持的 TEXT_PROVIDER: {provider}，可选: deepseek")


def create_multimodal_client(provider: str = "") -> BaseMultimodalClient:
    """多模态分析客户端。"""
    provider = provider or settings.MULTIMODAL_PROVIDER

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
    """按模型名选生图客户端：一一对应，未知模型报错。"""
    if model == "gpt-image-2":
        from app.llm.gpt_image_client import GptImageClient
        return GptImageClient(model=model)

    if model == "doubao-seedream-4-5-251128":
        from app.llm.seedream_image_client import SeedreamImageClient
        return SeedreamImageClient(model=model)

    raise ValueError(f"不支持的图片模型: {model}，当前支持: gpt-image-2 / doubao-seedream-4-5-251128")


def create_video_client(model: str = ""):
    """按视频模型选客户端：2.0 Mini 走 APIMart 中转，其余（含空值）走火山方舟。"""
    if model == "doubao-seedance-2-0-mini-260615":
        from app.services.seedance_apimart import ApimartSeedanceClient
        return ApimartSeedanceClient()

    from app.services.seedance_service import SeedanceService
    return SeedanceService()
