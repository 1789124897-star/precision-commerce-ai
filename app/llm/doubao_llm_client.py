"""豆包（火山方舟）多模态分析客户端。"""

import logging
import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import AppException
from app.llm.base import BaseMultimodalClient
from app.llm.http import post_with_retry

logger = logging.getLogger(__name__)


class DoubaoClient(BaseMultimodalClient):
    """豆包多模态客户端——图片 + 文本 → 分析报告。"""

    def __init__(self) -> None:
        self._api_key = settings.VOLCANO_API_KEY
        self._base_url = settings.DOUBAO_BASE_URL
        self._model = settings.DOUBAO_MODEL
        if not self._api_key:
            raise AppException("未配置 VOLCANO_API_KEY，请在 .env 中设置")
        if not self._base_url:
            raise AppException("未配置 DOUBAO_BASE_URL，请在 .env 中设置")
        if not self._model:
            raise AppException("未配置 DOUBAO_MODEL，请在 .env 中设置")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def analyze_multimodal(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: list[str],
    ) -> str:
        """图片 + 文本多模态分析，返回分析文本。"""
        content: list[dict[str, Any]] = []
        for url in image_data_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})
        content.append({"type": "text", "text": user_prompt})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0.5,
        }
        t0 = time.monotonic()
        logger.info("豆包多模态请求开始 model=%s images=%d", self._model, len(image_data_urls))
        data = await post_with_retry(self._base_url, payload, headers=self._headers, timeout=180.0)
        elapsed = time.monotonic() - t0
        logger.info("豆包多模态请求完成 耗时=%.1fs", elapsed)
        result_text: str = data["choices"][0]["message"]["content"]
        if not result_text:
            raise AppException("模型返回空内容", 502)
        return result_text
