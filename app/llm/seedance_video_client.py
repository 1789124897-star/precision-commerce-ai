"""Seedance 1.5 Pro（火山方舟）视频协议实现。"""

import asyncio
import json
import logging

import httpx

from app.core.config import settings
from app.core.exceptions import AppException
from app.llm.http import post_with_retry
from app.llm.video_client_base import VideoClientBase

logger = logging.getLogger(__name__)


class SeedanceService(VideoClientBase):
    """Seedance 1.5 pro 视频生成服务"""

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
        model: str = "",
    ) -> str:
        """提交 Seedance 1.5 pro 视频生成任务，返回 task_id。"""
        content: list = []

        if first_frame_url and last_frame_url:
            content.append({"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"})
            content.append({"type": "image_url", "image_url": {"url": last_frame_url}, "role": "last_frame"})
            mode = "图生视频-首尾帧"
        elif first_frame_url:
            content.append({"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"})
            mode = "图生视频-首帧"
        elif image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})
            mode = "图生视频-首帧"
        else:
            mode = "文生视频"

        if not (prompt or "").strip():
            raise AppException("缺少场景描述(prompt)，请填写后再生成", 400)

        content.append({"type": "text", "text": prompt})

        model = model or settings.SEEDANCE_VIDEO_MODEL
        payload = {
            "model": model,
            "content": content,
            "duration": int(duration_sec),
            "ratio": aspect_ratio,
            "generate_audio": generate_audio,
            "resolution": resolution,
        }

        audio_label = "有声" if generate_audio else "无声"
        logger.info(
            "Seedance 提交 [%s][%s]: model=%s duration=%ds prompt=%s...",
            mode, audio_label,
            model, int(duration_sec), prompt[:60],
        )

        try:
            resp_body = await post_with_retry(
                settings.SEEDANCE_VIDEO_URL,
                payload,
                headers={
                    "Authorization": f"Bearer {settings.VOLCANO_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=60,
                max_retries=1,
            )
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300]
            logger.error(f"Seedance 提交失败 HTTP {e.response.status_code}: {body}")
            raise AppException(f"Seedance 提交失败 HTTP {e.response.status_code}: {body[:120]}", 502) from e

        task_id = resp_body.get("id") or resp_body.get("taskId") or resp_body.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            logger.error(f"Seedance 响应无 task_id: {resp_body}")
            raise AppException("Seedance 响应缺少 task_id", 502)
        logger.info(f"Seedance 任务已提交: {task_id}")
        return task_id

    async def poll_task(self, task_id: str, poll_interval: float = 5.0, poll_max: int = 60) -> str:
        """轮询 Seedance 1.5 任务状态，返回 video_url。"""
        check_url = f"{settings.SEEDANCE_VIDEO_URL}/{task_id}"
        poll_fails = 0

        for attempt in range(poll_max):
            await asyncio.sleep(poll_interval)
            try:
                async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
                    resp = await client.get(
                        check_url,
                        headers={"Authorization": f"Bearer {settings.VOLCANO_API_KEY}"}
                    )
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError, httpx.RemoteProtocolError) as e:
                poll_fails += 1
                if poll_fails >= 5:
                    logger.error(f"轮询连续 {poll_fails} 次网络失败，放弃: {e}")
                    raise
                logger.warning(f"轮询第{attempt+1}次网络异常(连续{poll_fails}次)，继续下一轮: {e}")
                continue
            poll_fails = 0
            if resp.status_code != 200:
                logger.warning(f"轮询 HTTP {resp.status_code}: {resp.text[:200]}")
                continue

            data = resp.json()
            status = data.get("status", "")
            logger.info(f"Seedance 轮询 {attempt+1}/{poll_max}: status={status}")

            if status == "succeeded":
                video_url: str = data.get("content", {}).get("video_url")
                if video_url:
                    logger.info(f"Seedance 任务完成: {task_id} → {video_url}")
                    return video_url
                logger.warning(f"Seedance 已完成但无 video_url: {json.dumps(data, ensure_ascii=False)[:300]}")
                raise AppException("Seedance 任务完成但未返回视频 URL", 502)

            elif status == "failed":
                err_msg = data.get("error", {}).get("message", "任务失败")
                raise AppException(f"Seedance 任务失败: {err_msg[:120]}", 502)

        raise TimeoutError(f"Seedance 任务超时: {task_id} (轮询 {poll_max} 次)")
