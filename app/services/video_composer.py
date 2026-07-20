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

from app.core.paths import OUTPUT_DIR, VIDEO_DIR
from app.services.seedance_service import SeedanceService
from app.services.shot_grouper import ShotGrouper

logger = logging.getLogger(__name__)

# 中文字体路径 (相对于 app 包)
_FONT_DIRS = [
    Path(__file__).resolve().parent.parent.parent / "static" / "Z-SIMHEI.TTF",
    Path("static/Z-SIMHEI.TTF"),
]
FONT_PATH = next((p for p in _FONT_DIRS if p.exists()), None)


class VideoComposer:
    """Ken Burns 风格视频合成器"""

    # ── 共享工具 ──

    def _report(self, pct: float, stage: str, on_progress=None):
        """统一的进度报告器，供 compose / compose_premium 共用。"""
        if on_progress:
            on_progress(pct, stage)
        logger.info(f"[{pct*100:.0f}%] {stage}")

    @staticmethod
    def _make_encode_logger(encode_start: float, encode_end: float, on_progress=None):
        """工厂：创建编码进度 Logger，供 compose / compose_premium 共用。"""
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
        image_urls: list[str],
        audio_path: str,
        srt_path: str,
        task_id: str,
        aspect_ratio: str = "9:16",
        transition: str = "fade",
        quality_check: bool = True,
        on_progress: Callable[[float, str], None] | None = None,
    ) -> dict:
        """
        合成 Ken Burns 视频。

        Args:
            quality_check: 启用后使用 ffprobe 验证输出视频
            on_progress: 可选进度回调 (progress 0~1, stage_text)

        Returns:
            {"video_path": str, "duration_sec": float, "quality": dict|None}
        """
        def report(p, s):
            self._report(p, s, on_progress)

        # 解析分辨率
        w, h = self._parse_aspect(aspect_ratio)
        report(0.0, f"加载 {len(image_urls)} 张图片...")

        # 下载/加载图片
        images = self._load_local_images(image_urls)
        if not images:
            raise ValueError("没有可用的图片素材")

        # 加载音频（可选）
        report(0.05, "加载音频...")
        if audio_path:
            audio_local = self._to_local(audio_path)
            audio = AudioFileClip(str(audio_local))
            total_duration = audio.duration
            has_audio = True
        else:
            # 无音频：每张图默认 5s，总时长由图片数决定
            total_duration = len(images) * 5.0
            audio = None
            has_audio = False
            logger.info(f"无音频，静音视频 · {len(images)} 张图 × 5s = {total_duration:.1f}s")

        # 智能图片调度：最少不限（全部展示），最多 6s/张（不足时循环）
        MAX_PER_IMG = 6.0
        candidate = total_duration / len(images)
        if candidate > MAX_PER_IMG:
            # 图太少，每张最多放 6s，循环至覆盖音频
            per_img = MAX_PER_IMG
            loop_images = True
        else:
            # 图够多或刚好，每张按比例均分
            per_img = candidate
            loop_images = False
        logger.info(f"音频 {total_duration:.1f}s, {len(images)} 张图, 每张 {per_img:.1f}s, 循环={loop_images}")

        # 循环生成剪辑直到覆盖音频
        report(0.1, f"生成动画 (每张 {per_img:.1f}s)...")
        clips: list = []
        remaining = total_duration
        img_idx = 0
        while remaining > 0.1:
            clip_dur = min(per_img, remaining)
            clip = self._ken_burns_clip(images[img_idx % len(images)], w, h, clip_dur)
            if transition == "fade" and clips:
                clip = clip.with_effects([vfx.FadeIn(0.3)])
            clips.append(clip)
            remaining -= clip_dur
            img_idx += 1
            if loop_images:
                report(0.1 + 0.6 * remaining / total_duration, f"动画 {img_idx} (循环第 {img_idx//len(images)+1} 轮)")
            else:
                report(0.1 + 0.6 * (1 - remaining / total_duration), f"动画 {img_idx}/{len(images)}")

        # 拼接视频轨道
        report(0.7, "拼接音画...")
        video = concatenate_videoclips(clips, method="compose")
        if has_audio:
            video = video.with_audio(audio)

        # 叠加字幕
        if srt_path:
            local_srt = self._to_local(srt_path)
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

        # 导出 — 自定义进度 Logger 实时反馈编码百分比
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
            # 清理 MoviePy 临时文件
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

    def _parse_aspect(self, ratio: str) -> tuple[int, int]:
        """解析宽高比 -> (w, h)，基础边 1080px"""
        parts = ratio.replace(":", "/").split("/")
        if len(parts) != 2:
            return (1080, 1920)
        r = int(parts[0]) / int(parts[1])
        if r > 1:
            return (1920, 1080)
        if r < 1:
            return (1080, 1920)
        return (1080, 1080)

    def _to_local(self, url_or_path: str) -> Path:
        """将 /output/... 路径转为本地绝对路径"""
        if url_or_path.startswith("/output/"):
            local = url_or_path[len("/output/"):]
            return OUTPUT_DIR / local
        return Path(url_or_path)

    def _cleanup_temp_files(self):
        """清理 MoviePy 遗留的临时文件（如 TEMP_MPY_wvf_snd.mp4）"""
        cwd = Path.cwd()
        for pattern in ["TEMP_MPY_*", "temp_mpy_*"]:
            for f in cwd.glob(pattern):
                try:
                    f.unlink()
                    logger.info(f"已清理 MoviePy 临时文件: {f.name}")
                except OSError:
                    pass

    def _check_quality(self, video_path: Path, expected_duration: float) -> dict:
        """使用 ffprobe 验证输出视频质量。"""
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
        """从 URL 路径加载本地图片，不存在的跳过"""
        result = []
        for url in urls:
            local = self._to_local(url)
            if local.exists():
                result.append(local)
            else:
                logger.warning(f"图片不存在，跳过: {local}")
        return result

    def _ken_burns_clip(self, img_path: Path, w: int, h: int, duration: float) -> VideoClip:
        """Soft-blur background + centered Ken Burns animation."""
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
        """Parse SRT and generate subtitle ImageClip list."""
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
                start_sec = self._srt_time(start)
                end_sec = self._srt_time(end)
                text = " ".join(lines[2:])
                subtitles.append((start_sec, end_sec, text))
            except Exception:
                continue

        if not subtitles:
            return []

        # 加载字体
        font = self._load_font(48)

        clips = []
        for idx, (start_sec, end_sec, text) in enumerate(subtitles):
            duration = end_sec - start_sec
            if duration <= 0.1:
                continue

            # 渲染字幕图片
            img = self._render_text_image(text, font, w)
            if img is None:
                continue

            # 每条字幕用独立临时文件
            tmp = Path(tempfile.gettempdir()) / f"video_sub_{idx}.png"
            img.save(str(tmp))

            sub_clip = ImageClip(str(tmp), duration=duration)
            # 定位到底部 10%
            sub_clip = sub_clip.with_position(("center", int(h * 0.82)))
            sub_clip = sub_clip.with_start(start_sec)
            clips.append(sub_clip)

        return clips

    def _srt_time(self, t: str) -> float:
        h, m, rest = t.split(":")
        s, ms = rest.split(",") if "," in rest else (rest, "0")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        if FONT_PATH and FONT_PATH.exists():
            return ImageFont.truetype(str(FONT_PATH), size)
        return ImageFont.load_default()

    def _render_text_image(self, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> Image.Image | None:
        """渲染中文字幕图片：白字 + 黑阴影，无背景条"""
        margin = 30
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

        line_h = font.getbbox("测")[3] + 14
        img_h = line_h * len(lines) + margin
        img_w = max_w

        img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        for i, line in enumerate(lines):
            bbox = font.getbbox(line)
            text_w = bbox[2]
            x = (img_w - text_w) // 2
            y = margin // 2 + i * line_h
            draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 160))
            draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

        return img

    def compose_premium(
        self,
        shots: list[dict],
        images: list[str],
        audio_path: str,
        srt_path: str,
        task_id: str,
        aspect_ratio: str = "9:16",
        generate_audio: bool = False,
        on_progress: Callable[[float, str], None] | None = None,
        segment_durations: list[float] | None = None,
    ) -> dict:
        """精铺模式合成：按分镜列表生成场景展示视频。

        Args:
            shots: [{image_index, scene_prompt, duration_sec, overlay_text}, ...]
            images: 图片 URL 列表
            segment_durations: 每段口播的实际 TTS 时长（秒），非空时自动启动镜头组分组
        """
        def report(p, s):
            self._report(p, s, on_progress)

        w, h = self._parse_aspect(aspect_ratio)
        report(0.0, f"加载 {len(images)} 张图片...")

        local_images = self._load_local_images(images)
        # 图片可选：每个分镜会优先用 shot.image_url (Seedance)，失败则用本地图片，再失败则纯色占位

        # 加载音频（可选）
        report(0.03, "加载音频...")
        if audio_path:
            audio_local = self._to_local(audio_path)
            audio = AudioFileClip(str(audio_local))
            total_duration = audio.duration
            has_audio = True
        else:
            audio = None
            has_audio = False
            # 无外部音频时，用分镜时长之和作为总时长（Seedance 原生音频随视频片段保留）
            total_duration = 0  # 后续在分镜循环中累加

        # 按 shots 生成片段（Seedance AI 图生视频，失败回退 Ken Burns）
        total_shots = len(shots)
        total_design_dur = sum(s.get("duration_sec", 5) for s in shots)
        speed = total_design_dur / total_duration if total_duration > 0 else 1.0
        logger.info(f"精铺: {total_shots} 镜, 设计时长 {total_design_dur:.1f}s, 音频 {total_duration:.1f}s, 速率 {speed:.2f}")

        # ── 镜头组分组 ──
        # 有实际 TTS 时长时，将短段合并为镜头组，确保每组 ≥4s
        if segment_durations:
            grouper = ShotGrouper(min_dur=4.0, max_dur=12.0)
            shot_groups = grouper.group(shots, segment_durations)
            logger.info(f"镜头组分组: {len(shots)} 镜 → {len(shot_groups)} 组")
            # 统一迭代格式
            iterate_over = shot_groups
            use_groups = True
        else:
            # 无 TTS 时长时退化为原有 1:1 模式，但依然保证 ≥4s 底限
            iterate_over = [{
                "shots": [s],
                "tts_duration": s.get("duration_sec", 5),
                "seedance_dur": max(4, int(ceil(s.get("duration_sec", 5)))),
                "image_url": s.get("image_url", ""),
                "first_frame_url": s.get("first_frame_url", ""),
                "last_frame_url": s.get("last_frame_url", ""),
                "scene_prompt": s.get("scene_prompt", ""),
                "mode": "single",
            } for s in shots]
            use_groups = False

        clips: list = []
        time_elapsed = 0.0
        total_items = len(iterate_over)
        for i, group in enumerate(iterate_over):
            # 镜头组直接用已算好的 seedance_dur（已在 [4, 12] 内）
            dur = float(group["seedance_dur"])
            scene_prompt = group.get("scene_prompt", "")
            image_url = group.get("image_url", "")
            first_frame_url = group.get("first_frame_url", "")
            last_frame_url = group.get("last_frame_url", "")
            group_mode = group.get("mode", "single")
            segment_count = len(group.get("shots", [group]))
            # 预生成 clip：仅单段模式下使用
            pre_generated = group["shots"][0].get("clip_path", "") if group["shots"] else ""

            label = f"镜组{i+1}/{total_items}" if use_groups else f"分镜{i+1}/{total_items}"
            pct = 0.05 + (i / total_items) * 0.55
            report(pct, f"{label} {dur:.1f}s" + (f" ×{segment_count}段" if segment_count > 1 else ""))

            clip = None

            # 优先使用已预生成的分镜视频（仅单段模式）
            if pre_generated:
                pre_path = self._to_local(pre_generated)
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
                    seedance_path = asyncio.run(SeedanceService().generate_clip_first_last_frame(
                        first_frame_url=first_frame_url,
                        last_frame_url=last_frame_url,
                        prompt=scene_prompt or "smooth transition, professional product showcase",
                        aspect_ratio=aspect_ratio,
                        duration_sec=dur,
                        shot_index=i,
                        generate_audio=generate_audio,
                    ))
                    clip = VideoFileClip(str(seedance_path))
                    if clip.duration > dur + 1.5:
                        clip = clip.subclipped(0, dur)
                    logger.info(f"{label} 首尾帧完成: {clip.duration:.1f}s (目标 {dur}s, {segment_count}段)")
                except Exception as e:
                    logger.warning(f"{label} 首尾帧失败: {e}")

            # Seedance 图生视频（单图模式），失败回退 Ken Burns
            if clip is None and image_url and image_url.startswith("http"):
                try:
                    seedance_path = asyncio.run(SeedanceService().generate_clip_from_url(
                        image_url=image_url,
                        prompt=scene_prompt or "product showcase, professional lighting",
                        aspect_ratio=aspect_ratio,
                        duration_sec=dur,
                        shot_index=i,
                        generate_audio=generate_audio,
                    ))
                    clip = VideoFileClip(str(seedance_path))
                    if clip.duration > dur + 1.5:
                        clip = clip.subclipped(0, dur)
                    logger.info(f"{label} 图生视频完成: {clip.duration:.1f}s (目标 {dur}s)")
                except Exception as e:
                    logger.warning(f"{label} 图生视频失败: {e}")

            # 纯文生视频：无参考图，仅凭场景描述生成
            if clip is None and scene_prompt:
                try:
                    seedance_path = asyncio.run(SeedanceService().generate_clip_text_only(
                        prompt=scene_prompt,
                        aspect_ratio=aspect_ratio,
                        duration_sec=dur,
                        shot_index=i,
                    ))
                    clip = VideoFileClip(str(seedance_path))
                    if clip.duration > dur + 1.5:
                        clip = clip.subclipped(0, dur)
                    logger.info(f"{label} 文生视频完成: {clip.duration:.1f}s (目标 {dur}s)")
                except Exception as e:
                    logger.warning(f"{label} 文生视频失败: {e}")

            # Seedance 未启用或失败 → Ken Burns 回退
            if clip is None:
                if local_images:
                    # 镜头组用第一个 shot 的 image_index
                    first_shot = group["shots"][0] if group.get("shots") else group
                    img_idx = min(first_shot.get("image_index", 0), len(local_images) - 1)
                    clip = self._ken_burns_clip(local_images[img_idx], w, h, dur)
                else:
                    # 既无 URL 也无本地图片：生成纯色占位
                    logger.warning(f"{label} 无图片可用，使用占位")
                    clip = self._ken_burns_clip(
                        self._make_placeholder(w, h), w, h, dur
                    )

            if i > 0:
                clip = clip.with_effects([vfx.FadeIn(0.3)])
            clips.append(clip)
            time_elapsed += dur

        # 无外部音频时，用实际拼接时长作为总时长（Seedance 原生音频随视频保留）
        if not has_audio:
            total_duration = time_elapsed

        # 拼接
        report(0.62, "拼接音画...")
        video = concatenate_videoclips(clips, method="compose")
        if has_audio:
            video = video.with_audio(audio)

        # 叠加 SRT 字幕
        if srt_path:
            local_srt = self._to_local(srt_path)
            if local_srt.exists():
                report(0.75, "叠加字幕...")
                try:
                    subtitle_clips = self._render_srt(local_srt, w, h)
                    if subtitle_clips:
                        video = CompositeVideoClip([video] + subtitle_clips)
                except Exception as e:
                    logger.warning(f"字幕叠加失败: {e}")

        # 导出
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


# 全局单例
composer = VideoComposer()
