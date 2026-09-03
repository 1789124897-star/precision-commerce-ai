"""精铺模式合成：预生成分镜视频的纯拼装（不做 AI 生成）。"""
import logging
from collections.abc import Callable
from typing import Optional

from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)

from app.core.exceptions import AppException
from app.core.paths import VIDEO_DIR, from_output_url
from app.services.video_composer import VideoComposerBase

logger = logging.getLogger(__name__)


class PremiumVideoComposer(VideoComposerBase):
    """精铺模式合成器。"""

    def compose_premium(
        self,
        shots: list[dict],
        audio_path: str,
        srt_path: str,
        task_id: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> dict:

        def report(pct, stage):
            logger.info(f"[{pct*100:.0f}%] {stage}")
            if on_progress:
                on_progress(pct, stage)

        report(0.0, f"开始合成 {len(shots)} 个分镜...")
        if not shots:
            raise AppException("无分镜可合成", 502)

        # 阶段 1：准备资源 — 音频
        report(0.03, "加载音频...")
        has_audio = bool(audio_path)
        audio = None
        total_duration = 0.0
        if has_audio:
            audio = AudioFileClip(str(from_output_url(audio_path)))
            total_duration = audio.duration

        # 阶段 1：准备资源 — 分镜 clip
        clips: list = []
        time_elapsed = 0.0
        total_items = len(shots)
        for i, s in enumerate(shots):
            dur = float(max(4, s["duration_sec"]))
            label = f"分镜{i+1}/{total_items}"
            pre_generated = s.get("clip_path", "")

            report(0.05 + (i / total_items) * 0.55, f"{label} {dur:.1f}s")

            if not pre_generated:
                raise AppException(f"{label} 无预生成视频，无法合成", 502)
            pre_path = from_output_url(pre_generated)
            if not pre_path.exists():
                raise AppException(f"{label} 预生成 clip 不存在: {pre_path}", 502)
            try:
                clip = VideoFileClip(str(pre_path))
            except Exception as e:
                raise AppException(f"{label} 预生成 clip 加载失败: {e}", 502) from e
            if clip.duration > dur + 1.5:
                clip = clip.subclipped(0, dur)
            if i > 0:
                clip = clip.with_effects([vfx.FadeIn(0.3)])
            logger.info(f"{label} 使用预生成 clip: {clip.duration:.1f}s (目标 {dur:.1f}s)")
            clips.append(clip)
            time_elapsed += clip.duration

        if not has_audio:
            total_duration = time_elapsed

        # 阶段 2：视频拼装 + 音轨 + SRT
        report(0.62, "拼接音画...")
        video = concatenate_videoclips(clips, method="compose")
        if has_audio:
            video = video.with_audio(audio)

        if srt_path:
            local_srt = from_output_url(srt_path)
            logger.info(f"字幕路径: raw={srt_path!r} local={local_srt} exists={local_srt.exists()}")
            if local_srt.exists():
                report(0.75, "叠加字幕...")
                try:
                    subtitle_clips = self._render_srt(local_srt, video.w, video.h)
                    logger.info(f"字幕条数: {len(subtitle_clips)}")
                    if subtitle_clips:
                        video = CompositeVideoClip([video] + subtitle_clips)
                except Exception as e:
                    logger.warning(f"字幕叠加失败: {e}")

        # 编码导出
        out_name = f"{task_id}.mp4"
        out_path = VIDEO_DIR / out_name
        report(0.82, "正在编码视频...")

        encode_start = 0.82
        encode_end = 0.98
        encode_logger = self._make_encode_logger(encode_start, encode_end, on_progress)
        try:
            video.write_videofile(
                str(out_path),
                fps=25,
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                threads=4,
                logger=encode_logger,
            )

            report(1.0, "合成完成")
        finally:
            if audio is not None:
                audio.close()
            video.close()
            self._cleanup_temp_files()

        video_url = "/output/videos/" + out_name
        quality = self._check_quality(out_path, total_duration)
        return {"video_path": video_url, "duration_sec": round(total_duration, 1), "quality": quality}
