"""LLM 可插拔客户端层——基于工厂模式，所有提供者实现统一 BaseLLMClient 接口。"""
from app.llm.base import BaseLLMClient
from app.llm.factory import create_multimodal_client, create_text_client

__all__ = ["BaseLLMClient", "create_text_client", "create_multimodal_client"]
