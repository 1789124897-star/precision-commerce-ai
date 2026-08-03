"""DeepSeek 纯文本推理客户端。"""
import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import AppException
from app.llm.base import BaseLLMClient
from app.llm.http import post_with_retry

logger = logging.getLogger(__name__)


class DeepSeekClient(BaseLLMClient):
    """DeepSeek API 客户端"""

    def __init__(self) -> None:

        self._api_key = settings.TEXT_API_KEY
        self._base_url = settings.TEXT_BASE_URL
        self._model = settings.TEXT_MODEL
        if not self._api_key:
            raise AppException("未配置 TEXT_API_KEY，请在 .env 中设置")
        if not self._base_url:
            raise AppException("未配置 TEXT_BASE_URL，请在 .env 中设置")
        if not self._model:
            raise AppException("未配置 TEXT_MODEL，请在 .env 中设置")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 8192,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        t0 = time.monotonic()
        logger.info("DeepSeek 请求开始 model=%s max_tokens=%d", self._model, max_tokens)
        data = await post_with_retry(
            self._base_url, payload, headers=self._headers, timeout=120.0,
        )
        elapsed = time.monotonic() - t0
        logger.info("DeepSeek 请求完成 耗时=%.1fs", elapsed)
        content = data["choices"][0]["message"].get("content", "")
        if not content or not content.strip():
            finish_reason = data["choices"][0].get("finish_reason", "unknown")
            raise AppException(f"模型返回空内容，finish_reason={finish_reason}，请增大 max_tokens", 502)
        return content

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        t0 = time.monotonic()
        logger.info("DeepSeek 请求开始 model=%s max_tokens=%d", self._model, max_tokens)
        data = await post_with_retry(
            self._base_url, payload, headers=self._headers, timeout=120.0,
        )
        elapsed = time.monotonic() - t0
        logger.info("DeepSeek 请求完成 耗时=%.1fs", elapsed)
        content = data["choices"][0]["message"].get("content", "")
        if not content or not content.strip():
            finish_reason = data["choices"][0].get("finish_reason", "unknown")
            raise AppException(f"模型返回空内容，finish_reason={finish_reason}，请增大 max_tokens", 502)
        return json.loads(content)

    async def analyze_multimodal(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: list[str],
    ) -> str:
        raise NotImplementedError("DeepSeek 客户端未配置多模态能力")
