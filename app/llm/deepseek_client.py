"""DeepSeek 纯文本推理客户端。"""

import json
import logging
import time
from typing import Any, cast

from app.core.config import settings
from app.core.exceptions import AppException
from app.llm.base import BaseLLMClient
from app.llm.http import post_with_retry

logger = logging.getLogger(__name__)


class DeepSeekClient(BaseLLMClient):
    """DeepSeek API 客户端——文本推理"""

    def __init__(self) -> None:
        self._api_key = settings.DEEPSEEK_API_KEY
        self._base_url = settings.DEEPSEEK_BASE_URL
        self._model = settings.DEEPSEEK_MODEL
        if not self._api_key:
            raise AppException("未配置 DEEPSEEK_API_KEY，请在 .env 中设置")
        if not self._base_url:
            raise AppException("未配置 DEEPSEEK_BASE_URL，请在 .env 中设置")
        if not self._model:
            raise AppException("未配置 DEEPSEEK_MODEL，请在 .env 中设置")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        """开启 DeepSeek 原生 JSON 模式，直接返回 dict。"""
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
        logger.info("DeepSeek JSON 请求开始 model=%s", self._model)
        data = await post_with_retry(self._base_url, payload, headers=self._headers, timeout=120.0)
        elapsed = time.monotonic() - t0
        logger.info("DeepSeek JSON 请求完成 耗时=%.1fs", elapsed)
        content = data["choices"][0]["message"].get("content", "")
        if not content or not content.strip():
            finish_reason = data["choices"][0].get("finish_reason", "unknown")
            if finish_reason == "length":
                raise AppException("JSON 输出被截断，请增大 max_tokens 或精简 prompt", 502)
            if finish_reason == "content_filter":
                raise AppException("内容被安全策略拦截，请修改 prompt 后重试", 502)
            raise AppException(f"DeepSeek JSON Output 返回空内容（已知问题，finish_reason={finish_reason}），请重试", 502)
        return cast("dict[str, Any]", json.loads(content))
