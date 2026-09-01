"""视频合成服务 — MoviePy Ken Burns + 字幕叠加 + Seedance AI 图生视频"""
import asyncio
import logging
import random
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from math import ceil
from pathlib import Path
from typing import Optional

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    VideoClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from proglog import ProgressBarLogger

from app.core.exceptions import AppException
from app.core.paths import VIDEO_DIR, from_output_url
from app.core.srt_utils import srt_to_seconds
from app.services.image_host import image_host
from app.services.shot_service import ShotService

logger = logging.getLogger(__name__)

# 中文字体路径
_FONT_DIRS = [
    Path(__file__).resolve().parent.parent.parent / "static" / "Z-SIMHEI.TTF",
    Path("static/Z-SIMHEI.TTF"),
]
FONT_PATH = next((p for p in _FONT_DIRS if p.exists()), None)


class VideoComposer:
    """Ken Burns 风格视频合成器"""

    @staticmethod
    def _make_encode_logger(encode_start: float, encode_end: float, on_progress=None):
        """编码进度 Logger 工厂"""
        class _EncodeLogger(ProgressBarLogger):
            total_frames = 0
            def bars_callback(self, bar, attr, value, old_value=None):
                if bar == "frame_index" and attr == "total":
                    self.total_frames = value
                elif bar == "frame_index" and attr == "index" and self.total_frames:
                    pct = encode_start + (value / self.total_frames) * (encode_end - encode_start)
                    if on_progress:
                        on_progress(round(pct, 3), f"编码中 {value}/{self.total_frames} 帧")
        return _EncodeLogger()

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

    # ── 私有方法 ──

    def _parse_aspect(self, ratio: str, resolution: str = "720p") -> tuple[int, int]:
        """宽高比 + 分辨率 → (w, h)"""
        base_map = {"480p": 480, "720p": 720, "1080p": 1080}
        short = base_map.get(resolution, 720)
        parts = ratio.replace(":", "/").split("/")
        if len(parts) != 2:
            return (short, int(short * 16 / 9))  # 默认竖屏
        r = int(parts[0]) / int(parts[1])
        if r > 1:
            # 横屏：高为短边
            return (int(short * r), short)
        if r < 1:
            # 竖屏：宽为短边
            return (short, int(short / r))
        return (short, short)

    def _cleanup_temp_files(self):
        """清理 MoviePy 临时文件"""
        cwd = Path.cwd()
        for pattern in ["TEMP_MPY_*", "temp_mpy_*"]:
            for f in cwd.glob(pattern):
                try:
                    f.unlink()
                    logger.info(f"已清理 MoviePy 临时文件: {f.name}")
                except OSError:
                    pass

    def _check_quality(self, video_path: Path, expected_duration: float) -> dict:
        """ffprobe 验证视频质量"""
        result: dict = {
            "passed": True,
            "warnings": [],
            "video_duration_sec": None,
            "file_size_mb": None,
        }
        if not video_path.exists():
            result["passed"] = False
            result["warnings"].append("输出文件不存在")
            return result

        file_size_mb = video_path.stat().st_size / (1024 * 1024)
        result["file_size_mb"] = round(file_size_mb, 1)
        if file_size_mb < 0.1:
            result["passed"] = False
            result["warnings"].append(f"视频文件过小 ({file_size_mb:.1f}MB)")

        try:
            proc = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                actual_dur = float(proc.stdout.strip())
                result["video_duration_sec"] = round(actual_dur, 1)
                drift = abs(actual_dur - expected_duration)
                if drift > 1.0:
                    result["warnings"].append(
                        f"视频时长偏差 {drift:.1f}s (期望 {expected_duration:.1f}s, 实际 {actual_dur:.1f}s)"
                    )
                if actual_dur < 0.5:
                    result["passed"] = False
                    result["warnings"].append(f"视频时长异常 ({actual_dur:.1f}s)")
                logger.info(f"质量检查: duration={actual_dur:.1f}s, size={file_size_mb:.1f}MB, passed={result['passed']}")
            else:
                result["warnings"].append("ffprobe 解析失败（可能缺少 ffprobe）")
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError) as e:
            result["warnings"].append(f"质量检查跳过: {e}")
            logger.debug(f"质量检查失败 (非致命): {e}")

        if not result["warnings"]:
            result["warnings"] = None
        return result

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

    def _make_placeholder(self, w: int, h: int) -> Path:
        img = Image.new("RGB", (w, h), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        try:
            font = self._load_font(32)
            txt = "未设置参考图"
            bb = font.getbbox(txt)
            tw = bb[2] - bb[0]
            th = bb[3] - bb[1]
            draw.text(((w - tw)//2, (h - th)//2), txt, font=font, fill=(150,150,150))
        except Exception:
            pass
        tmp = Path(tempfile.gettempdir()) / f"ph_{uuid.uuid4().hex[:8]}.jpg"
        img.save(str(tmp), quality=85)
        return tmp

    def _render_srt(self, srt_path: Path, w: int, h: int) -> list:
        """解析 SRT → MoviePy 字幕 clip 列表"""
        if not srt_path.exists():
            return []

        content = srt_path.read_text(encoding="utf-8-sig")
        blocks = content.strip().split("\n\n")
        subtitles = []
        for block in blocks:
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if len(lines) < 3:
                continue
            try:
                time_line = lines[1]
                start, end = time_line.split(" --> ")
                start_sec = srt_to_seconds(start)
                end_sec = srt_to_seconds(end)
                text = " ".join(lines[2:])
                subtitles.append((start_sec, end_sec, text))
            except Exception:
                continue

        if not subtitles:
            return []

        # 字号：短边的 7.8%
        font_size = int(min(w, h) * 0.078)
        font = self._load_font(font_size)
        # 阴影：字号 4%，至少 2px
        shadow = max(2, int(font_size * 0.04))

        clips = []
        for idx, (start_sec, end_sec, text) in enumerate(subtitles):
            duration = end_sec - start_sec
            if duration <= 0.1:
                continue

            # 渲染字幕图片
            img = self._render_text_image(text, font, w, shadow)
            if img is None:
                continue

            # 每条字幕用独立临时文件
            tmp = Path(tempfile.gettempdir()) / f"video_sub_{idx}.png"
            img.save(str(tmp))

            sub_clip = ImageClip(str(tmp), duration=duration)
            # 字幕垂直位置：不同宽高比适配不同平台底部 UI
            if w < h:
                # 竖屏 9:16 → 抖音，留 18% 
                y_pos = int(h * 0.82)
            elif w > h:
                # 横屏 16:9 → YouTube，留 12%
                y_pos = int(h * 0.88)
            else:
                # 方屏 1:1 → Instagram，留 15%
                y_pos = int(h * 0.85)
            sub_clip = sub_clip.with_position(("center", y_pos))
            sub_clip = sub_clip.with_start(start_sec)
            clips.append(sub_clip)

        return clips

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        if FONT_PATH and FONT_PATH.exists():
            logger.info(f"加载字体: {FONT_PATH} size={size}")
            return ImageFont.truetype(str(FONT_PATH), size)
        logger.warning("未找到中文字体，使用默认字体（中文可能不显示）")
        return ImageFont.load_default()

    def _render_text_image(self, text: str, font: ImageFont.FreeTypeFont, max_w: int, shadow: int = 2) -> Optional[Image.Image]:
        """字幕渲染：白字黑边，无背景条"""
        margin = int(max_w * 0.04)  # 左右留白 4%
        lines = []
        current = ""
        for char in text:
            test = current + char
            if font.getbbox(test)[2] > max_w - margin * 2:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)

        if not lines:
            return None

        # 行高：字高 + 30% 间距
        line_h = font.getbbox("测")[3] + int(font.size * 0.3)
        img_h = line_h * len(lines) + margin
        img_w = max_w

        img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        for i, line in enumerate(lines):
            bbox = font.getbbox(line)
            text_w = bbox[2]
            x = (img_w - text_w) // 2
            y = margin // 2 + i * line_h
            draw.text((x + shadow, y + shadow), line, font=font, fill=(0, 0, 0, 180))
            draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

        return img

    def compose_premium(
        self,
        shots: list[dict],
        images: list[str],
        audio_path: str,
        srt_path: str,
        task_id: str,
        aspect_ratio: str = "",
        resolution: str = "",
        generate_audio: bool = False,
        on_progress: Optional[Callable[[float, str], None]] = None,
        segment_durations: Optional[list[float]] = None,  # noqa: ARG002
        seedance_model: str = "",  # 前端选的视频模型，决定走火山方舟还是 APIMart
    ) -> dict:
        """精品模式：按分镜列表逐镜生成视频"""
        aspect_ratio = aspect_ratio or "9:16"
        resolution = resolution or "720p"
        def report(pct, stage):
            logger.info(f"[{pct*100:.0f}%] {stage}")
            if on_progress:
                on_progress(pct, stage)

        w, h = self._parse_aspect(aspect_ratio, resolution)

        # 预生成分镜到齐 → 跳过图片加载
        all_pregen = all(s.get("clip_path", "") for s in shots)
        if all_pregen:
            local_images = []
            report(0.0, f"{len(shots)} 个预生成分镜就绪，跳过图片加载")
        else:
            report(0.0, f"加载 {len(images)} 张图片...")
            local_images = self._load_local_images(images)

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
            # 无外部音频，时长按分镜累加
            total_duration = 0

        # 逐镜生成：Seedance → 失败回退 Ken Burns
        total_shots = len(shots)
        total_design_dur = sum(s.get("duration_sec", 5) for s in shots)
        speed = total_design_dur / total_duration if total_duration > 0 else 1.0
        logger.info(f"精铺: {total_shots} 镜, 设计时长 {total_design_dur:.1f}s, 音频 {total_duration:.1f}s, 速率 {speed:.2f}")

        # ── 1:1 模式，每个 shot 视为一个镜头组 ──
        iterate_over = [{
            "shots": [s],
            "tts_duration": s.get("duration_sec", 5),
            "seedance_dur": max(4, int(ceil(s.get("duration_sec", 5)))),
            "first_frame_url": s.get("first_frame_url", ""),
            "last_frame_url": s.get("last_frame_url", ""),
            "scene_prompt": s.get("scene_prompt", ""),
            "mode": "single",
        } for s in shots]

        clips: list = []
        time_elapsed = 0.0
        total_items = len(iterate_over)
        for i, group in enumerate(iterate_over):
            dur = float(group["seedance_dur"])
            scene_prompt = group.get("scene_prompt", "")
            scene_prompt_en = group.get("scene_prompt_en", "")  # 英文 → Seedance
            seedance_prompt = scene_prompt_en or scene_prompt  # 优先英文，兜底中文
            first_frame_url = group.get("first_frame_url", "")
            last_frame_url = group.get("last_frame_url", "")
            # 本地图片 → 公网 URL（Seedance 只接受公网可访问图片）
            try:
                first_frame_url = image_host.to_public(first_frame_url)
                last_frame_url = image_host.to_public(last_frame_url)
            except Exception as e:
                logger.warning(f"{label} 图片公网化失败，回退 Ken Burns: {e}")
                first_frame_url = last_frame_url = ""
            group_mode = group.get("mode", "single")
            segment_count = len(group.get("shots", [group]))
            # 单段模式优先用预生成 clip
            pre_generated = group["shots"][0].get("clip_path", "") if group["shots"] else ""

            label = f"分镜{i+1}/{total_items}"
            pct = 0.05 + (i / total_items) * 0.55
            report(pct, f"{label} {dur:.1f}s" + (f" ×{segment_count}段" if segment_count > 1 else ""))

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

            # ── 镜头组首尾帧模式（多段合并） ──
            if clip is None and group_mode == "first_last" and first_frame_url and last_frame_url:
                try:
                    seedance_path = asyncio.run(ShotService().generate_clip(
                        model=seedance_model,
                        prompt=seedance_prompt,
                        first_frame_url=first_frame_url,
                        last_frame_url=last_frame_url,
                        aspect_ratio=aspect_ratio,
                        duration_sec=dur,
                        shot_index=i,
                        generate_audio=generate_audio,
                        resolution=resolution,
                    ))
                    clip = VideoFileClip(str(seedance_path))
                    if clip.duration > dur + 1.5:
                        clip = clip.subclipped(0, dur)
                    logger.info(f"{label} 首尾帧完成: {clip.duration:.1f}s (目标 {dur}s, {segment_count}段)")
                except Exception as e:
                    logger.warning(f"{label} 首尾帧失败: {e}")

            # Seedance 图生视频，失败回退 Ken Burns
            if clip is None and first_frame_url and first_frame_url.startswith("http"):
                try:
                    seedance_path = asyncio.run(ShotService().generate_clip(
                        model=seedance_model,
                        prompt=seedance_prompt,
                        image_url=first_frame_url,
                        aspect_ratio=aspect_ratio,
                        duration_sec=dur,
                        shot_index=i,
                        generate_audio=generate_audio,
                        resolution=resolution,
                    ))
                    clip = VideoFileClip(str(seedance_path))
                    if clip.duration > dur + 1.5:
                        clip = clip.subclipped(0, dur)
                    logger.info(f"{label} 图生视频完成: {clip.duration:.1f}s (目标 {dur}s)")
                except Exception as e:
                    logger.warning(f"{label} 图生视频失败: {e}")

            # 纯文生视频：无参考图
            if clip is None and seedance_prompt:
                try:
                    seedance_path = asyncio.run(ShotService().generate_clip(
                        model=seedance_model,
                        prompt=seedance_prompt,
                        aspect_ratio=aspect_ratio,
                        duration_sec=dur,
                        shot_index=i,
                        resolution=resolution,
                    ))
                    clip = VideoFileClip(str(seedance_path))
                    if clip.duration > dur + 1.5:
                        clip = clip.subclipped(0, dur)
                    logger.info(f"{label} 文生视频完成: {clip.duration:.1f}s (目标 {dur}s)")
                except Exception as e:
                    logger.warning(f"{label} 文生视频失败: {e}")

            # Seedance 失败 → Ken Burns 回退
            if clip is None:
                if local_images:
                    # 镜头组取第一个 shot 的图片索引
                    first_shot = group["shots"][0] if group.get("shots") else group
                    img_idx = min(first_shot.get("image_index", 0), len(local_images) - 1)
                    clip = self._ken_burns_clip(local_images[img_idx], w, h, dur)
                else:
                    # 无 URL 也无本地图片 → 纯色占位
                    logger.warning(f"{label} 无图片可用，使用占位")
                    clip = self._ken_burns_clip(
                        self._make_placeholder(w, h), w, h, dur
                    )

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

