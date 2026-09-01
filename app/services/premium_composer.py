"""精铺模式合成：预生成分镜视频的纯拼装（不做 AI 生成）。"""
import logging
from collections.abc import Callable
from math import ceil
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
        aspect_ratio: str = "",
        resolution: str = "",
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> dict:
        aspect_ratio = aspect_ratio or "9:16"
        resolution = resolution or "720p"
        def report(pct, stage):
            logger.info(f"[{pct*100:.0f}%] {stage}")
            if on_progress:
                on_progress(pct, stage)

        w, h = self._parse_aspect(aspect_ratio, resolution)

        report(0.0, f"开始合成 {len(shots)} 个分镜...")

        # 加载音频
        report(0.03, "加载音频...")
        if audio_path:
            audio_local = from_output_url(audio_path)
            audio = AudioFileClip(str(audio_local))
            total_duration = audio.duration
            has_audio = True
        else:
            audio = None
            has_audio = False
            total_duration = 0

        total_design_dur = sum(s.get("duration_sec", 5) for s in shots)
        speed = total_design_dur / total_duration if total_duration > 0 else 1.0
        logger.info(f"精铺: {len(shots)} 镜, 设计时长 {total_design_dur:.1f}s, 音频 {total_duration:.1f}s, 速率 {speed:.2f}")

        clips: list = []
        time_elapsed = 0.0
        total_items = len(shots)
        for i, s in enumerate(shots):
            dur = float(max(4, int(ceil(s.get("duration_sec", 5)))))
            label = f"分镜{i+1}/{total_items}"
            pre_generated = s.get("clip_path", "")

            pct = 0.05 + (i / total_items) * 0.55
            report(pct, f"{label} {dur:.1f}s")

            clip = None

            # 预生成 clip 存在则直接复用
            if pre_generated:
                pre_path = from_output_url(pre_generated)
                if pre_path.exists():
                    try:
                        clip = VideoFileClip(str(pre_path))
                        if clip.duration > dur + 1.5:
                            clip = clip.subclipped(0, dur)
                        logger.info(f"{label} 使用预生成 clip: {clip.duration:.1f}s (目标 {dur:.1f}s)")
                    except Exception as e:
                        logger.warning(f"{label} 预生成 clip 加载失败: {e}")
                else:
                    logger.warning(f"{label} 预生成 clip 不存在: {pre_path}")

            # 无预生成视频 → 直接失败
            if clip is None:
                raise AppException(f"{label} 无预生成视频，无法合成", 502)

            if i > 0:
                clip = clip.with_effects([vfx.FadeIn(0.3)])
            clips.append(clip)
            time_elapsed += dur

        # 无外部音频，用实际拼接时长
        if not has_audio:
            total_duration = time_elapsed

        # 拼接视频
        report(0.62, "拼接音画...")
        video = concatenate_videoclips(clips, method="compose")
        video = video.resized((w, h))
        if has_audio:
            video = video.with_audio(audio)

        # 叠加 SRT 字幕
        if srt_path:
            local_srt = from_output_url(srt_path)
            logger.info(f"字幕路径: raw={srt_path!r} local={local_srt} exists={local_srt.exists()}")
            if local_srt.exists():
                report(0.75, "叠加字幕...")
                try:
                    subtitle_clips = self._render_srt(local_srt, w, h)
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
            if has_audio:
                audio.close()
            video.close()
            self._cleanup_temp_files()

        video_url = "/output/videos/" + out_name
        quality = self._check_quality(out_path, total_duration)
        return {"video_path": video_url, "duration_sec": round(total_duration, 1), "quality": quality}
