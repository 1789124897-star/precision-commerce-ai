"""AI 生图服务"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.core.paths import IMAGE_DIR
from app.core.utils import image_to_data_url
from app.services.ai_client import AIClient

logger = logging.getLogger(__name__)


class ImageGenService:
    """AI 生图服务"""

    def __init__(self):
        self.ai = AIClient()

    async def run(
        self,
        images_data: str = "",
        ref_image_paths: list[str] | None = None,
        size: str = "2048x2048",
        task_id: str = "",
    ) -> dict:
        if not settings.SEEDREAM_IMAGE_URL or not settings.SEEDREAM_IMAGE_MODEL:
            raise ValueError("未配置图片生成 API，请在 .env 中设置 SEEDREAM_IMAGE_URL 和 SEEDREAM_IMAGE_MODEL")

        ref_data_urls = [image_to_data_url(url) for url in ref_image_paths] if ref_image_paths else []

        output_dir = IMAGE_DIR / task_id
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        specs = json.loads(images_data)
        results = await self.ai.generate_images(
            specs=specs,
            ref_image_data_urls=ref_data_urls,
            size=size,
        )
        all_images = await _build_image_entries(results, "", output_dir, task_id, timestamp)

        success_count = sum(1 for r in results if r.get("url"))
        if success_count == 0:
            errors = [r.get("error", "?") for r in results]
            first_error = next((e for e in errors if e != "internal error"), errors[0])
            raise RuntimeError(f"全部 {len(results)} 张图片生成失败: {errors.count(first_error)}/{len(results)} 张报 {first_error}")

        return {
            "images": all_images,
            "output_dir": str(output_dir),
        }

    def run_sync(self, **kwargs: Any) -> dict:
        """同步包装，供 Celery 任务调用"""
        return asyncio.run(self.run(**kwargs))


async def _download_image(url: str, output_dir: Path, filename: str) -> Path:
    """下载图片到本地，返回保存路径"""
    filepath = output_dir / filename
    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        filepath.write_bytes(resp.content)
    return filepath


async def _build_image_entries(
    results: list[dict[str, Any]],
    prefix: str,
    output_dir: Path,
    task_id: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    """将生图结果 + 下载组装为统一条目列表"""
    entries = []
    for r in results:
        src = r.get("source", prefix or "img")
        img_info = {
            "position": r["position"],
            "type": r.get("type", prefix),
            "prompt": r["prompt"],
            "local_path": "",
            "remote_url": r.get("url", ""),
            "error": r.get("error", ""),
        }
        if r.get("url"):
            try:
                local_path = await _download_image(
                    r["url"],
                    output_dir,
                    f"{task_id}_{src}_pos{r['position']}_{timestamp}.png",
                )
                img_info["local_path"] = str(local_path)
            except Exception as e:
                img_info["error"] = f"下载失败: {e}"
        entries.append(img_info)
    return entries
