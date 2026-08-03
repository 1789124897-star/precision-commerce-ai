"""豆包（火山方舟）多模态分析客户端。"""
import logging
import time
from typing import Any

from app.core.config import settings
from app.llm.base import BaseLLMClient
from app.llm.http import post_with_retry

logger = logging.getLogger(__name__)


class DoubaoClient(BaseLLMClient):
    """豆包多模态客户端——图片 + 文本 → 分析报告。

    通过 settings.DOUBAO_BASE_URL / settings.VOLCANO_API_KEY 配置火山方舟接入点。
    """

    def __init__(self) -> None:
        self._api_key = settings.VOLCANO_API_KEY
        self._base_url = settings.DOUBAO_BASE_URL
        self._model = settings.DOUBAO_MODEL
        if not self._api_key:
            raise ValueError("未配置 VOLCANO_API_KEY，请在 .env 中设置")
        if not self._base_url:
            raise ValueError("未配置 DOUBAO_BASE_URL，请在 .env 中设置")
        if not self._model:
            raise ValueError("未配置 DOUBAO_MODEL，请在 .env 中设置")

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
        raise NotImplementedError("豆包纯文本推理请使用 DeepSeekClient")

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        raise NotImplementedError("豆包 JSON 推理请使用 DeepSeekClient")

    async def analyze_multimodal(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: list[str],
    ) -> str:
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
            raise ValueError("模型返回空内容")
        return result_text
