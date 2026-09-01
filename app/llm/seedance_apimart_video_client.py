"""APIMart 中转 Seedance 2.0 Mini 视频客户端 """
import asyncio
import json
import logging
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.exceptions import AppException
from app.llm.http import post_with_retry
from app.llm.video_client_base import VideoClientBase

logger = logging.getLogger(__name__)


class ApimartSeedanceClient(VideoClientBase):
    """Seedance 2.0 Mini 视频生成服务（APIMart 中转）"""

    def __init__(self, model: str = ""):
        self.model = model or settings.APIMART_VIDEO_MODEL
        self.proxy = settings.APIMART_PROXY or None  # 中转站需代理访问

    async def submit_task(
        self,
        image_url: str = "",
        prompt: str = "",
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        first_frame_url: str = "",
        last_frame_url: str = "",
        generate_audio: bool = False,
        resolution: str = "720p",
    ) -> str:
        """提交 APIMart 视频生成任务，返回 task_id。"""
        if not (prompt or "").strip():
            raise AppException("缺少场景描述(prompt)，请填写后再生成", 400)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": aspect_ratio,
            "duration": int(duration_sec),
            "generate_audio": generate_audio,
            "resolution": resolution,
        }

        if first_frame_url and last_frame_url:
            payload["image_with_roles"] = [
                {"url": first_frame_url, "role": "first_frame"},
                {"url": last_frame_url, "role": "last_frame"},
            ]
            mode = "图生视频-首尾帧"
        elif image_url:
            payload["image_urls"] = [image_url]
            mode = "图生视频-首帧"
        else:
            mode = "文生视频"

        audio_label = "有声" if generate_audio else "无声"
        logger.info(
            "APIMart 提交 [%s][%s]: model=%s duration=%ds prompt=%s...",
            mode, audio_label, self.model, int(duration_sec), prompt[:60],
        )

        try:
            resp_body = await post_with_retry(
                settings.APIMART_VIDEO_URL,
                payload,
                headers={
                    "Authorization": f"Bearer {settings.APIMART_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=60,
                max_retries=1, 
                proxy=self.proxy,
            )
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300]
            logger.error(f"APIMart 提交失败 HTTP {e.response.status_code}: {body}")
            raise AppException(f"APIMart 提交失败 HTTP {e.response.status_code}: {body[:120]}", 502) from e

        data = resp_body.get("data") or {}
        task_id = data[0].get("task_id") if isinstance(data, list) and data else data.get("task_id")
        if not task_id:
            logger.error(f"APIMart 响应无 task_id: {resp_body}")
            raise AppException("APIMart 响应缺少 task_id", 502)
        logger.info(f"APIMart 任务已提交: {task_id}")
        return task_id

    async def poll_task(self, task_id: str, poll_interval: float = 5.0, poll_max: int = 60) -> str:
        """轮询 APIMart 任务状态。"""
        check_url = f"{settings.APIMART_VIDEO_TASK_URL}/{task_id}"
        poll_fails = 0

        for attempt in range(poll_max):
            await asyncio.sleep(poll_interval)
            try:
                async with httpx.AsyncClient(timeout=30, trust_env=False, proxy=self.proxy) as client:
                    resp = await client.get(
                        check_url,
                        headers={"Authorization": f"Bearer {settings.APIMART_API_KEY}"},
                    )
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError, httpx.RemoteProtocolError) as e:
                poll_fails += 1
                if poll_fails >= 5:
                    logger.error(f"APIMart 轮询连续 {poll_fails} 次网络失败，放弃: {e}")
                    raise
                logger.warning(f"APIMart 轮询第{attempt+1}次网络异常(连续{poll_fails}次)，继续下一轮: {e}")
                continue
            poll_fails = 0
            if resp.status_code != 200:
                logger.warning(f"APIMart 轮询 HTTP {resp.status_code}: {resp.text[:200]}")
                continue

            data = resp.json().get("data") or {}
            status = data.get("status", "")
            logger.info(f"APIMart 轮询 {attempt+1}/{poll_max}: status={status} progress={data.get('progress')}")

            if status == "completed":
                videos = (data.get("result") or {}).get("videos") or []
                if not videos:
                    logger.warning(f"APIMart 已完成但无 videos: {json.dumps(data, ensure_ascii=False)[:300]}")
                    raise AppException("APIMart 任务完成但未返回视频", 502)
                raw = videos[0].get("url") or videos[0].get("video_url")
                video_url = raw[0] if isinstance(raw, list) else raw
                if video_url:
                    logger.info(f"APIMart 任务完成: {task_id} → {video_url}")
                    return video_url
                logger.warning(f"APIMart 已完成但无 video_url: {json.dumps(data, ensure_ascii=False)[:300]}")
                raise AppException("APIMart 任务完成但未返回视频 URL", 502)

            elif status in ("failed", "cancelled"):
                err_msg = (data.get("error") or {}).get("message", "任务失败")
                raise AppException(f"APIMart 任务{status}: {err_msg[:120]}", 502)

        raise TimeoutError(f"APIMart 任务超时: {task_id} (轮询 {poll_max} 次)")

    async def download_video(self, video_url: str, output_path: Path) -> Path:
        """下载视频文件。"""
        logger.info(f"下载视频: {video_url} → {output_path}")
        return await self._download_with_retry(video_url, output_path, proxy=self.proxy)
