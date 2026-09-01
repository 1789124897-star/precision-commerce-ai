"""分镜生成服务：分镜策略 + 客户端路由，run_sync 供 Celery 任务调用。"""
import asyncio
import logging
from pathlib import Path
from typing import Any

from app.core.exceptions import AppException
from app.llm.factory import create_video_client
from app.services.image_host import ImageTunnelError, image_host

logger = logging.getLogger(__name__)


class ShotService:
    """分镜生成服务——校验/拼台词/分流策略，按 seedance_model 路由视频客户端。"""

    async def generate_shot(
        self,
        *,
        first_frame_url: str = "",
        last_frame_url: str = "",
        prompt: str = "",
        voiceover: str = "",
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        shot_index: int = 0,
        on_progress=None,
        generate_audio: bool = False,
        resolution: str = "720p",
        seedance_model: str = "",
    ) -> Path:
        """异步分镜生成：图片公网化 → 拼台词 → 校验 → 首尾帧/图生/文生分流。"""
        if not seedance_model:
            logger.info("未指定视频模型，降级默认 Seedance 1.5 Pro")
        client = create_video_client(seedance_model)

        try:
            first_frame_url = image_host.to_public(first_frame_url)
            last_frame_url = image_host.to_public(last_frame_url)
        except ImageTunnelError as exc:
            raise AppException(f"图片公网化失败: {exc}", 502) from exc

        if voiceover and generate_audio:
            prompt = f"{prompt}\n台词：{voiceover}" if prompt else f"台词：{voiceover}"
        if not prompt.strip():
            raise AppException(f"[镜{shot_index+1}] 缺少场景描述，请填写后再生成", 400)

        if first_frame_url and last_frame_url:
            return await client.generate_clip(
                prompt=prompt,
                first_frame_url=first_frame_url,
                last_frame_url=last_frame_url,
                aspect_ratio=aspect_ratio,
                duration_sec=duration_sec,
                shot_index=shot_index,
                on_progress=on_progress,
                generate_audio=generate_audio,
                resolution=resolution,
            )
        if first_frame_url and first_frame_url.startswith("http"):
            return await client.generate_clip(
                prompt=prompt,
                image_url=first_frame_url,
                aspect_ratio=aspect_ratio,
                duration_sec=duration_sec,
                shot_index=shot_index,
                on_progress=on_progress,
                generate_audio=generate_audio,
                resolution=resolution,
            )
        return await client.generate_clip(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            duration_sec=duration_sec,
            shot_index=shot_index,
            on_progress=on_progress,
            generate_audio=generate_audio,
            resolution=resolution,
        )

    async def generate_clip(self, *, model: str = "", **kwargs: Any) -> Path:
        """细粒度视频片段生成。"""
        return await create_video_client(model).generate_clip(**kwargs)

    def run_sync(self, **kwargs: Any) -> Path:
        """同步分镜入口。"""
        return asyncio.run(self.generate_shot(**kwargs))
