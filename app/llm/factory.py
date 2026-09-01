"""LLM 客户端工厂"""

from app.llm.base import BaseImageClient, BaseLLMClient, BaseMultimodalClient, BaseVideoClient


def create_text_client(model: str = "") -> BaseLLMClient:
    """纯文本客户端"""
    if model == "deepseek-v4-pro":
        from app.llm.deepseek_llm_client import DeepSeekClient
        return DeepSeekClient(model=model)

    if model == "deepseek-v4-flash":
        from app.llm.deepseek_llm_client import DeepSeekClient
        return DeepSeekClient(model=model)

    if not model:  # 默认 deepseek-v4-pro
        from app.llm.deepseek_llm_client import DeepSeekClient
        return DeepSeekClient(model="deepseek-v4-pro")

    raise ValueError(f"不支持的文本模型: {model}，当前支持: deepseek-v4-pro / deepseek-v4-flash")


def create_multimodal_client(model: str = "") -> BaseMultimodalClient:
    """多模态客户端"""
    if model == "gpt-5.6-sol":
        from app.llm.gpt_multimodal_client import GptMultimodalClient
        return GptMultimodalClient()

    if model == "doubao-1-5-vision-pro-32k-250115":
        from app.llm.doubao_llm_client import DoubaoClient
        return DoubaoClient()

    if model == "kimi-k3":
        from app.llm.kimi_llm_client import KimiClient
        return KimiClient()

    if not model:  # 默认 gpt-5.6-sol
        from app.llm.gpt_multimodal_client import GptMultimodalClient
        return GptMultimodalClient()

    raise ValueError(f"不支持的多模态模型: {model}，当前支持: gpt-5.6-sol / doubao-1-5-vision-pro-32k-250115 / kimi-k3")


def create_image_client(model: str = "") -> BaseImageClient:
    """生图客户端"""
    if model == "gpt-image-2":
        from app.llm.gpt_image_client import GptImageClient
        return GptImageClient(model=model)

    if model == "doubao-seedream-4-5-251128":
        from app.llm.seedream_image_client import SeedreamImageClient
        return SeedreamImageClient(model=model)

    if not model:  # 默认 gpt-image-2
        from app.llm.gpt_image_client import GptImageClient
        return GptImageClient(model="gpt-image-2")

    raise ValueError(f"不支持的图片模型: {model}，当前支持: gpt-image-2 / doubao-seedream-4-5-251128")


def create_video_client(model: str = "") -> BaseVideoClient:
    """视频模型选客户端."""
    if model == "doubao-seedance-1-5-pro-251215":
        from app.llm.seedance_video_client import SeedanceService
        return SeedanceService()

    if model == "doubao-seedance-2-0-mini-260615":
        from app.llm.seedance_apimart_video_client import ApimartSeedanceClient
        return ApimartSeedanceClient()

    if not model:  # 默认 doubao-seedance-1-5-pro-251215
        from app.llm.seedance_video_client import SeedanceService
        return SeedanceService()

    raise ValueError(f"不支持的视频模型: {model}，当前支持 doubao-seedance-1-5-pro-251215 / doubao-seedance-2-0-mini-260615")
