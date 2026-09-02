"""快速模式合成：图片 + 音频 + 字幕 → Ken Burns 动画视频。"""
import logging
import random
from collections.abc import Callable
from pathlib import Path
from typing import Optional

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    VideoClip,
    concatenate_videoclips,
    vfx,
)
from PIL import Image, ImageFilter

from app.core.exceptions import AppException
from app.core.paths import VIDEO_DIR, from_output_url
from app.services.video_composer import VideoComposerBase

logger = logging.getLogger(__name__)


class QuickVideoComposer(VideoComposerBase):
    """快速模式合成器：图片 Ken Burns 动画（不调用 AI）。"""

    def compose(
        self,
        images: list[str],
        audio_path: str,
        srt_path: str,
        task_id: str,
        aspect_ratio: str = "",
        resolution: str = "",
        transition: str = "fade",
        quality_check: bool = True,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> dict:
        """快速模式：图片 + 音频 + 字幕 → MP4

        on_progress: 进度回调 (0~1, stage_text)
        返回: {"video_path", "duration_sec", "quality"}
        """
        aspect_ratio = aspect_ratio or "9:16"
        resolution = resolution or "720p"
        def report(pct, stage):
            logger.info(f"[{pct*100:.0f}%] {stage}")
            if on_progress:
                on_progress(pct, stage)

        # 解析宽高比
        w, h = self._parse_aspect(aspect_ratio, resolution)
        report(0.0, f"加载 {len(images)} 张图片...")

        # 下载/加载图片
        image_paths = self._load_local_images(images)
        if not image_paths:
            raise AppException("没有可用的图片素材", 400)

        # 加载音频
        report(0.05, "加载音频...")
        if audio_path:
            audio_local = from_output_url(audio_path)
            audio = AudioFileClip(str(audio_local))
            total_duration = audio.duration
            has_audio = True
        else:
            # 无音频：每张图 2s
            total_duration = len(image_paths) * 2.0
            audio = None
            has_audio = False
            logger.info(f"无音频，静音视频 · {len(image_paths)} 张图 × 2s = {total_duration:.1f}s")

        # 每张图最多 6s，不够就循环
        MAX_PER_IMG = 6.0
        candidate = total_duration / len(image_paths)
        if candidate > MAX_PER_IMG:
            # 图不够 → 循环
            per_img = MAX_PER_IMG
            loop_images = True
        else:
            # 图够多 → 均分
            per_img = candidate
            loop_images = False
        logger.info(f"音频 {total_duration:.1f}s, {len(image_paths)} 张图, 每张 {per_img:.1f}s, 循环={loop_images}")

        # 逐图生成 Ken Burns 动画
        report(0.1, f"生成动画 (每张 {per_img:.1f}s)...")
        clips: list = []
        remaining = total_duration
        img_idx = 0
        while remaining > 0.1:
            clip_dur = min(per_img, remaining)
            clip = self._ken_burns_clip(image_paths[img_idx % len(image_paths)], w, h, clip_dur)
            if clips:
                clip = self._apply_transition(clip, transition)
            clips.append(clip)
            remaining -= clip_dur
            img_idx += 1
            if loop_images:
                report(0.1 + 0.6 * remaining / total_duration, f"动画 {img_idx} (循环第 {img_idx//len(image_paths)+1} 轮)")
            else:
                report(0.1 + 0.6 * (1 - remaining / total_duration), f"动画 {img_idx}/{len(image_paths)}")

        # 拼接视频
        report(0.7, "拼接音画...")
        video = concatenate_videoclips(clips, method="compose")
        if has_audio:
            video = video.with_audio(audio)

        # 叠加字幕
        if srt_path:
            local_srt = from_output_url(srt_path)
            logger.info(f"字幕路径: raw={srt_path!r} local={local_srt} exists={local_srt.exists()}")
            report(0.8, "叠加字幕...")
            try:
                subtitle_clips = self._render_srt(local_srt, w, h)
                logger.info(f"字幕条数: {len(subtitle_clips)}")
                if subtitle_clips:
                    video = CompositeVideoClip([video] + subtitle_clips)
                else:
                    logger.warning(f"字幕解析为空，文件内容: {local_srt.read_text(encoding='utf-8-sig')[:200] if local_srt.exists() else '不存在'}")
            except Exception as e:
                logger.warning(f"字幕叠加失败，跳过: {e}")

        # 编码导出
        out_name = f"{task_id}.mp4"
        out_path = VIDEO_DIR / out_name
        report(0.85, "正在编码视频...")

        encode_start = 0.85
        encode_end = 0.99
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
        quality = None
        if quality_check:
            report(1.0, "质量检查中...")
            quality = self._check_quality(out_path, total_duration)

        return {"video_path": video_url, "duration_sec": round(total_duration, 1), "quality": quality}

    def _load_local_images(self, urls: list[str]) -> list[Path]:
        """URL → 本地路径，不存在的跳过"""
        result = []
        for url in urls:
            local = from_output_url(url)
            if local.exists():
                result.append(local)
            else:
                logger.warning(f"图片不存在，跳过: {local}")
        return result

    def _ken_burns_clip(self, img_path: Path, w: int, h: int, duration: float) -> VideoClip:
        """模糊背景 + Ken Burns 缩放动画"""
        pil_img = Image.open(img_path).convert("RGB")
        iw, ih = pil_img.size

        # ── 背景层：缩放填满画布 + 轻模糊 ──
        bg_scale = max(w / iw, h / ih)
        bg = pil_img.resize((int(iw * bg_scale), int(ih * bg_scale)), Image.LANCZOS)
        left = (bg.size[0] - w) // 2
        top = (bg.size[1] - h) // 2
        bg = bg.crop((left, top, left + w, top + h))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=8))
        bg_np = np.array(bg)

        # ── 前景层：等比例缩放适配画布 92% ──
        fg_scale = min((w * 0.92) / iw, (h * 0.92) / ih)
        fg_w, fg_h = int(iw * fg_scale), int(ih * fg_scale)

        # Ken Burns 微缩放 (3%~7%)
        zoom = 1.03 + random.random() * 0.04
        fg_zw, fg_zh = int(fg_w * zoom), int(fg_h * zoom)
        fg_zoomed = pil_img.resize((fg_zw, fg_zh), Image.LANCZOS)
        fg_np = np.array(fg_zoomed)

        def make_frame(t):
            frame = bg_np.copy()
            ox = (w - fg_zw) // 2
            oy = (h - fg_zh) // 2
            frame[oy:oy + fg_zh, ox:ox + fg_zw] = fg_np
            return frame

        clip = VideoClip(make_frame, duration=duration)
        clip = clip.with_effects([vfx.FadeIn(0.3), vfx.FadeOut(0.3)])
        return clip

    @staticmethod
    def _apply_transition(clip: VideoClip, transition: str) -> VideoClip:
        """非首帧 clip 添加转场"""
        if transition == "slide":
            direction = random.choice(["left", "right", "top", "bottom"])
            return clip.with_effects([vfx.SlideIn(0.4, direction)])
        if transition == "zoom":
            return clip.with_effects([vfx.CrossFadeIn(0.4)])
        if transition == "random":
            t = random.choice([
                lambda c: c.with_effects([vfx.FadeIn(0.3)]),
                lambda c: c.with_effects([vfx.SlideIn(0.4, random.choice(["left", "right"]))]),
                lambda c: c.with_effects([vfx.CrossFadeIn(0.4)]),
            ])
            return t(clip)
        # fade 或未知 → 默认淡入
        return clip.with_effects([vfx.FadeIn(0.3)])
