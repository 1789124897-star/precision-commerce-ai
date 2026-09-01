"""视频客户端公共实现：生成流水线 + 图床/下载/进度。"""

import asyncio
import logging
from abc import abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.paths import VIDEO_DIR
from app.llm.base import BaseVideoClient
from app.services.image_host import ImageTunnelError, image_host

logger = logging.getLogger(__name__)


class VideoClientBase(BaseVideoClient):
    """视频客户端公共实现：生成流水线 + 图床/下载/进度。"""

    @abstractmethod
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
        """提交视频生成任务，返回 task_id。"""
        ...

    @abstractmethod
    async def poll_task(self, task_id: str, poll_interval: float = 5.0, poll_max: int = 60) -> str:
        """轮询任务状态，返回 video_url。"""
        ...

    @staticmethod
    def _notify(stage: str, detail: str, shot_index: int, on_progress=None):
        """进度通知器：写日志 + 回调。"""
        logger.info(f"[镜{shot_index+1}] {stage} {detail}")
        if on_progress:
            try:
                on_progress(stage, detail)
            except Exception:
                pass

    async def generate_clip(
        self,
        prompt: str,
        image_url: str = "",
        first_frame_url: str = "",
        last_frame_url: str = "",
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        shot_index: int = 0,
        on_progress: Optional[Callable] = None,
        generate_audio: bool = False,
        resolution: str = "720p",
    ) -> Path:
        """异步片段流水线：提交→轮询→下载，按首尾帧/图生/文生分流。"""
        image_url = self._to_public(image_url)
        first_frame_url = self._to_public(first_frame_url)
        last_frame_url = self._to_public(last_frame_url)
        if first_frame_url and last_frame_url:
            stage_label, prefix = "首尾帧生成", "seedance_f2l_shot"
        elif image_url:
            stage_label, prefix = "提交生成", "seedance_shot"
        else:
            stage_label, prefix = "文生视频", "seedance_t2v_shot"

        def notify(s, d=""):
            self._notify(s, d, shot_index, on_progress)

        notify(stage_label, f"prompt: {prompt[:50]}...")
        task_id = await self.submit_task(
            image_url=image_url, 
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

        output_path = VIDEO_DIR / f"{prefix}_shot{shot_index}_{task_id[:8]}.mp4"
        notify("下载视频", str(output_path.name))
        await self.download_video(video_url, output_path)

        notify("完成", str(output_path))
        return output_path

    def _to_public(self, url_or_path: str) -> str:
        """本地图片路径 → 公网 URL。"""
        try:
            return image_host.to_public(url_or_path)
        except ImageTunnelError as exc:
            raise AppException(f"图片公网化失败: {exc}", 502) from exc

    async def _download_with_retry(self, video_url: str, output_path: Path, proxy: Optional[str] = None) -> Path:
        """下载视频：网络异常最多重试 3 次（间隔 3/6s）；失败时错误信息带视频地址便于用户自查。"""
        last_err = ""
        for attempt in range(1, 4):
            try:
                async with httpx.AsyncClient(timeout=120, trust_env=False, proxy=proxy, follow_redirects=True) as client:
                    resp = await client.get(video_url)
                    if resp.status_code != 200:
                        raise AppException(f"视频下载失败 HTTP {resp.status_code}，地址: {video_url}", 502)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(resp.content)
                logger.info(f"视频已保存: {output_path} ({output_path.stat().st_size} bytes)")
                return output_path
            except AppException:
                raise
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                if attempt < 3:
                    wait = 3 * attempt
                    logger.warning(f"视频下载失败(第{attempt}次)，{wait}s 后重试: {last_err}")
                    await asyncio.sleep(wait)
        raise AppException(f"视频下载失败(重试3次): {last_err}，地址: {video_url}", 502)

    async def download_video(self, video_url: str, output_path: Path) -> Path:
        """下载视频到本地。"""
        logger.info(f"下载视频: {video_url} → {output_path}")
        return await self._download_with_retry(video_url, output_path)
