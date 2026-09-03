"""Seedream（火山方舟）生图客户端。"""

import logging
import time
from typing import Optional

from app.core.config import settings
from app.core.exceptions import AppException
from app.llm.base import BaseImageClient
from app.llm.http import post_with_retry

logger = logging.getLogger(__name__)


class SeedreamImageClient(BaseImageClient):
    """Seedream 生图客户端——提示词 + 参考图 → 图片 URL。"""

    def __init__(self, model: Optional[str] = None) -> None:
        self._model = model or settings.SEEDREAM_IMAGE_MODEL
        if not settings.SEEDREAM_IMAGE_URL:
            raise AppException("未配置 SEEDREAM_IMAGE_URL，请在 .env 中设置")
        if not self._model:
            raise AppException("未配置 SEEDREAM_IMAGE_MODEL，请在 .env 中设置")
        if not settings.VOLCANO_API_KEY:
            raise AppException("未配置 VOLCANO_API_KEY，请在 .env 中设置")

    async def generate_image(
        self,
        *,
        prompt: str,
        size: str,
        ref_image_data_urls: list[str],
    ) -> str:
        """单张生图，返回图片 URL。"""
        headers = {"Authorization": f"Bearer {settings.VOLCANO_API_KEY}"}
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "size": size,
            "response_format": "url",
            "stream": False,
            "watermark": False,
        }
        if ref_image_data_urls:
            payload["image"] = ref_image_data_urls
            payload["sequential_image_generation"] = "disabled"

        logger.info("Seedream 生图: model=%s size=%s prompt_len=%d ref_images=%d", self._model, size, len(prompt), len(ref_image_data_urls))
        t0 = time.monotonic()
        data = await post_with_retry(
            settings.SEEDREAM_IMAGE_URL,
            payload,
            headers=headers,
        )
        elapsed = time.monotonic() - t0
        logger.info("Seedream 生图完成 耗时=%.1fs", elapsed)
        try:
            url = data["data"][0]["url"]
            return str(url)
        except (KeyError, IndexError, TypeError) as e:
            raise AppException(f"生图响应缺少 url: {str(data)[:200]}", 502) from e
