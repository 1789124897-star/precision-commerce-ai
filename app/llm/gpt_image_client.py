"""GPT（OpenAI 兼容）生图客户端。"""

import base64
import logging
import time
import uuid
from typing import Optional

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.paths import UPLOAD_DIR
from app.llm.base import BaseImageClient
from app.llm.http import post_with_retry

logger = logging.getLogger(__name__)

# 前端尺寸 
_ASPECT_HINT = {
    "2048x2048": "1:1 方形构图",
    "1920x1920": "1:1 方形构图",
    "2560x1440": "16:9 横屏构图",
    "1440x2560": "9:16 竖屏构图",
}

_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _data_url_to_file(data_url: str) -> tuple[str, bytes, str]:
    """参考图 data URL → httpx multipart 文件元组 (filename, bytes, mime)。"""
    header, _, b64 = data_url.partition(",")
    mime = header.split(";", 1)[0].split(":", 1)[-1] or "image/png"
    ext = _EXT_BY_MIME.get(mime, ".png")
    return f"ref{ext}", base64.b64decode(b64), mime


class GptImageClient(BaseImageClient):
    """GPT 生图客户端"""

    def __init__(self, model: Optional[str] = None) -> None:
        self._model = model or "gpt-image-2"
        if not settings.GPT_IMAGE_URL:
            raise AppException("未配置 GPT_IMAGE_URL，请在 .env 中设置")
        if not settings.GPT_API_KEY:
            raise AppException("未配置 GPT_API_KEY，请在 .env 中设置")

    async def generate_image(
        self,
        *,
        prompt: str,
        size: str,
        ref_image_data_urls: list[str],
    ) -> str:
        """单张生图，参考图时走 edits 接口（multipart image[]），否则走 generations 接口。"""
        hint = _ASPECT_HINT.get(size)
        if hint:
            prompt = f"{prompt}。{hint}"

        logger.info("GPT 生图: model=%s size=%s prompt_len=%d ref_images=%d", self._model, size, len(prompt), len(ref_image_data_urls))
        t0 = time.monotonic()

        headers = {"Authorization": f"Bearer {settings.GPT_API_KEY}"}
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "size": "1024x1024",  # 占位：sudocode 忽略该参数，比例由 prompt 画幅描述控制
            "response_format": "url",
        }

        if ref_image_data_urls:
            url = settings.GPT_IMAGE_URL.rsplit("/", 1)[0] + "/edits"
            files = [("image[]", _data_url_to_file(d)) for d in ref_image_data_urls]
            logger.info("GPT 生图(edits): ref_images=%d", len(ref_image_data_urls))
        else:
            url = settings.GPT_IMAGE_URL
            files = None

        data = await post_with_retry(
            url,
            payload,
            headers=headers,
            proxy=settings.GPT_PROXY or None,
            files=files,
        )
        elapsed = time.monotonic() - t0
        logger.info("GPT 生图完成 耗时=%.1fs", elapsed)

        try:
            img = data["data"][0]
        except (KeyError, IndexError, TypeError) as e:
            raise AppException(f"生图响应缺少 data: {str(data)[:200]}", 502) from e

        url = img.get("url") or ""
        if url.startswith("http"):
            return url

        b64 = url.split(",", 1)[1] if url.startswith("data:") else img.get("b64_json")
        if not b64:
            raise AppException(f"生图响应无 url/b64_json: {str(img)[:200]}", 502)

        raw = base64.b64decode(b64)
        filename = f"gpt_{uuid.uuid4().hex[:8]}.png"
        filepath = UPLOAD_DIR / filename
        filepath.write_bytes(raw)
        return f"/output/uploads/{filename}"
