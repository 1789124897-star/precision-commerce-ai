"""Seedance 图生视频服务 — 图片上传 → API 提交 → 轮询 → 下载"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable, Optional

import httpx

from app.core.config import settings
from app.core.paths import VIDEO_DIR as SEEDANCE_VIDEO_DIR

logger = logging.getLogger(__name__)


class SeedanceService:
    """Seedance 1.5 pro 视频生成服务"""

    @staticmethod
    def _notify(stage: str, detail: str, shot_index: int, on_progress=None):
        """统一的进度通知器，供所有 generate_clip_* 方法共用。"""
        logger.info(f"[镜{shot_index+1}] {stage} {detail}")
        if on_progress:
            try:
                on_progress(stage, detail)
            except Exception:
                pass

    # ── 图床上传 ──

    async def _upload_to_smms(self, image_path: Path) -> str:
        """上传本地图片到 sm.ms，返回公网 URL。"""
        logger.info(f"上传图片到 sm.ms: {image_path}")

        async with httpx.AsyncClient(timeout=30) as client:
            with open(image_path, "rb") as f:
                resp = await client.post(
                    "https://smms.app/api/v2/upload",
                    files={"smfile": (image_path.name, f, "image/jpeg")},
                    headers={"User-Agent": "Precision-Commerce-AI/1.0"},
                )
            data = resp.json()
            if data.get("success"):
                url = data["data"]["url"]
                logger.info(f"上传成功: {url}")
                return url
            msg = data.get("message", "unknown")
            logger.warning(f"sm.ms 上传失败 ({msg})，尝试 imgse...")
            raise RuntimeError(f"sm.ms upload failed: {msg}")

    async def _upload_to_imgse(self, image_path: Path) -> str:
        """imgse.com 备用图床。"""
        async with httpx.AsyncClient(timeout=30) as client:
            with open(image_path, "rb") as f:
                resp = await client.post(
                    "https://imgse.com/api/v1/upload",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    headers={"User-Agent": "Precision-Commerce-AI/1.0"},
                )
            data = resp.json()
            if data.get("status") and data.get("data", {}).get("links", {}).get("url"):
                url = data["data"]["links"]["url"]
                logger.info(f"imgse 上传成功: {url}")
                return url
            raise RuntimeError(f"imgse upload failed: {resp.text[:200]}")

    async def upload_to_public_url(self, image_path: Path) -> str:
        """上传本地图片到公开 URL（sm.ms → imgse 备选）。"""
        try:
            return await self._upload_to_smms(image_path)
        except Exception:
            try:
                return await self._upload_to_imgse(image_path)
            except Exception:
                raise RuntimeError(
                    f"图片上传失败（sm.ms + imgse 均不可用）: {image_path}"
                )

    # ── Seedance API 核心 ──

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
        """提交 Seedance 1.5 pro 视频生成任务，返回 task_id。

        支持模式：
        - image_url 非空 → 图生视频-首帧（image-to-video）
        - first_frame_url + last_frame_url → 图生视频-首尾帧
        - 仅 prompt → 纯文生视频（text-to-video）
        - generate_audio=True → 有声视频
        """
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

        content.append({"type": "text", "text": prompt or "product showcase, professional lighting"})

        payload = {
            "model": settings.SEEDANCE_VIDEO_MODEL,
            "content": content,
            "duration": int(duration_sec),
            "ratio": aspect_ratio,
            "generate_audio": generate_audio,
            "resolution": resolution,
        }

        audio_label = "有声" if generate_audio else "无声"
        logger.info(
            f"Seedance 提交 [{mode}][{audio_label}]: model=%s duration=%ds prompt=%s...",
            settings.SEEDANCE_VIDEO_MODEL, int(duration_sec), prompt[:60],
        )

        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            resp = await client.post(
                settings.SEEDANCE_VIDEO_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            data = resp.json()
            if resp.status_code != 200:
                body = resp.text[:300]
                logger.error(f"Seedance 提交失败 HTTP {resp.status_code}: {body}")
                raise RuntimeError(f"Seedance API error {resp.status_code}: {body}")

            task_id = data.get("id") or data.get("taskId") or data.get("task_id")
            if not task_id:
                logger.error(f"Seedance 响应无 task_id: {resp.text[:300]}")
                raise RuntimeError(f"Seedance 响应缺少 task_id: {resp.text[:200]}")
            logger.info(f"Seedance 任务已提交: {task_id}")
            return task_id

    async def poll_task(self, task_id: str, poll_interval: float = 5.0, poll_max: int = 60) -> str:
        """轮询 Seedance 1.5 任务状态，返回 video_url。"""
        check_url = f"{settings.SEEDANCE_VIDEO_URL}/{task_id}"

        for attempt in range(poll_max):
            await asyncio.sleep(poll_interval)
            async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
                resp = await client.get(
                    check_url,
                    headers={"Authorization": f"Bearer {settings.API_KEY}"},
                )
                if resp.status_code != 200:
                    logger.warning(f"轮询 HTTP {resp.status_code}: {resp.text[:200]}")
                    continue

                data = resp.json()
                status = data.get("status", "")
                logger.info(f"Seedance 轮询 {attempt+1}/{poll_max}: status={status}")

                if status == "succeeded":
                    video_url = data.get("content", {}).get("video_url")
                    if video_url:
                        logger.info(f"Seedance 任务完成: {task_id} → {video_url}")
                        return video_url
                    logger.warning(f"Seedance 已完成但无 video_url: {json.dumps(data, ensure_ascii=False)[:300]}")
                    raise RuntimeError("Seedance 任务完成但未返回视频 URL")

                elif status == "failed":
                    err_msg = data.get("error", {}).get("message", "任务失败")
                    raise RuntimeError(f"Seedance 任务失败: {err_msg}")

        raise TimeoutError(f"Seedance 任务超时: {task_id} (轮询 {poll_max} 次)")

    async def download_video(self, video_url: str, output_path: Path) -> Path:
        """下载 Seedance 生成的视频到本地。"""
        logger.info(f"下载视频: {video_url} → {output_path}")
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            resp = await client.get(video_url, follow_redirects=True)
            if resp.status_code != 200:
                raise RuntimeError(f"视频下载失败 HTTP {resp.status_code}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(resp.content)
        logger.info(f"视频已保存: {output_path} ({output_path.stat().st_size} bytes)")
        return output_path

    # ── 视频生成流程 ──

    async def generate_clip(
        self,
        image_path: Path,
        prompt: str,
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        shot_index: int = 0,
        on_progress: Optional[Callable] = None,
        generate_audio: bool = False,
        resolution: str = "720p",
    ) -> Path:
        """完整流程：上传图片 → 提交 Seedance → 轮询 → 下载 → 返回本地视频路径。"""

        notify = lambda s, d="": self._notify(s, d, shot_index, on_progress)

        notify("上传图片", f"{image_path.name}")
        public_url = await self.upload_to_public_url(image_path)

        notify("提交生成", f"prompt: {prompt[:50]}...")
        task_id = await self.submit_task(public_url, prompt, aspect_ratio, duration_sec, generate_audio=generate_audio, resolution=resolution)

        notify("等待生成", f"task: {task_id}")
        video_url = await self.poll_task(
            task_id,
            poll_interval=settings.SEEDANCE_POLL_INTERVAL,
            poll_max=settings.SEEDANCE_POLL_MAX,
        )

        output_path = SEEDANCE_VIDEO_DIR / f"seedance_shot{shot_index}_{task_id[:8]}.mp4"
        notify("下载视频", str(output_path.name))
        await self.download_video(video_url, output_path)

        notify("完成", str(output_path))
        return output_path

    async def generate_clip_from_url(
        self,
        image_url: str,
        prompt: str,
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        shot_index: int = 0,
        on_progress: Optional[Callable] = None,
        generate_audio: bool = False,
        resolution: str = "720p",
    ) -> Path:
        """直接从公网 URL 调 Seedance（图生视频-首帧），跳过图床上传。"""

        notify = lambda s, d="": self._notify(s, d, shot_index, on_progress)

        notify("提交生成", f"url: {image_url[:50]}... prompt: {prompt[:50]}...")
        task_id = await self.submit_task(image_url, prompt, aspect_ratio, duration_sec, generate_audio=generate_audio, resolution=resolution)

        notify("等待生成", f"task: {task_id}")
        video_url = await self.poll_task(
            task_id,
            poll_interval=settings.SEEDANCE_POLL_INTERVAL,
            poll_max=settings.SEEDANCE_POLL_MAX,
        )

        output_path = SEEDANCE_VIDEO_DIR / f"seedance_shot{shot_index}_{task_id[:8]}.mp4"
        notify("下载视频", str(output_path.name))
        await self.download_video(video_url, output_path)

        notify("完成", str(output_path))
        return output_path

    async def generate_clip_text_only(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        shot_index: int = 0,
        on_progress: Optional[Callable] = None,
        generate_audio: bool = False,
        resolution: str = "720p",
    ) -> Path:
        """纯文生视频：无参考图，仅靠 prompt 描述生成。"""

        notify = lambda s, d="": self._notify(s, d, shot_index, on_progress)

        notify("文生视频", f"prompt: {prompt[:60]}...")
        task_id = await self.submit_task(
            image_url="", prompt=prompt, aspect_ratio=aspect_ratio,
            duration_sec=duration_sec, generate_audio=generate_audio, resolution=resolution,
        )

        notify("等待生成", f"task: {task_id}")
        video_url = await self.poll_task(
            task_id,
            poll_interval=settings.SEEDANCE_POLL_INTERVAL,
            poll_max=settings.SEEDANCE_POLL_MAX,
        )

        output_path = SEEDANCE_VIDEO_DIR / f"seedance_t2v_shot{shot_index}_{task_id[:8]}.mp4"
        notify("下载视频", str(output_path.name))
        await self.download_video(video_url, output_path)

        notify("完成", str(output_path))
        return output_path

    async def generate_clip_first_last_frame(
        self,
        first_frame_url: str,
        last_frame_url: str,
        prompt: str,
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        shot_index: int = 0,
        on_progress: Optional[Callable] = None,
        generate_audio: bool = False,
        resolution: str = "720p",
    ) -> Path:
        """图生视频-首尾帧：指定首帧和尾帧图片，AI 生成中间过渡视频。"""

        notify = lambda s, d="": self._notify(s, d, shot_index, on_progress)

        notify("首尾帧生成", f"prompt: {prompt[:50]}...")
        task_id = await self.submit_task(
            image_url="",
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            duration_sec=duration_sec,
            first_frame_url=first_frame_url,
            last_frame_url=last_frame_url,
            generate_audio=generate_audio,
            resolution=resolution,
        )

        notify("等待生成", f"task: {task_id}")
        video_url = await self.poll_task(
            task_id,
            poll_interval=settings.SEEDANCE_POLL_INTERVAL,
            poll_max=settings.SEEDANCE_POLL_MAX,
        )

        output_path = SEEDANCE_VIDEO_DIR / f"seedance_f2l_shot{shot_index}_{task_id[:8]}.mp4"
        notify("下载视频", str(output_path.name))
        await self.download_video(video_url, output_path)

        notify("完成", str(output_path))
        return output_path

    # ── 分镜入口 ──

    async def generate_shot(
        self,
        image_url: str = "",
        first_frame_url: str = "",
        last_frame_url: str = "",
        prompt: str = "",
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        shot_index: int = 0,
        on_progress=None,
        generate_audio: bool = False,
        resolution: str = "720p",
    ) -> Path:
        """分镜生成入口：根据输入自动选择首尾帧/图生/文生模式。"""
        if first_frame_url and last_frame_url:
            return await self.generate_clip_first_last_frame(
                first_frame_url=first_frame_url,
                last_frame_url=last_frame_url,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                duration_sec=duration_sec,
                shot_index=shot_index,
                on_progress=on_progress,
                generate_audio=generate_audio,
                resolution=resolution,
            )
        if image_url and image_url.startswith("http"):
            return await self.generate_clip_from_url(
                image_url=image_url,
                prompt=prompt or "product showcase",
                aspect_ratio=aspect_ratio,
                duration_sec=duration_sec,
                shot_index=shot_index,
                on_progress=on_progress,
                generate_audio=generate_audio,
                resolution=resolution,
            )
        return await self.generate_clip_text_only(
            prompt=prompt or "product showcase",
            aspect_ratio=aspect_ratio,
            duration_sec=duration_sec,
            shot_index=shot_index,
            on_progress=on_progress,
            generate_audio=generate_audio,
            resolution=resolution,
        )

    def generate_shot_sync(self, **kwargs) -> Path:
        """同步包装，供 Celery 任务调用"""
        return asyncio.run(self.generate_shot(**kwargs))
