"""LLM 客户端工厂。"""

from app.llm.base import BaseLLMClient


def create_text_client() -> BaseLLMClient:
    """创建纯文本推理客户端。"""
    from app.llm.deepseek_client import DeepSeekClient
    return DeepSeekClient()


def create_multimodal_client() -> BaseLLMClient:
    """创建多模态分析客户端。"""
    from app.llm.doubao_client import DoubaoClient
    return DoubaoClient()
