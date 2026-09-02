"""视频合成公共实现：字幕渲染 / 画幅解析 / 质量检查 / 编码日志。"""
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from moviepy import ImageClip
from PIL import Image, ImageDraw, ImageFont
from proglog import ProgressBarLogger

from app.core.srt_utils import srt_to_seconds

logger = logging.getLogger(__name__)

# 中文字体路径：首选霞鹜文楷（字幕观感），缺失时回退中易黑体
_FONT_DIRS = [
    Path(__file__).resolve().parent.parent.parent / "static" / "LXGWWenKai-Regular.ttf",
    Path("static/LXGWWenKai-Regular.ttf"),
    Path(__file__).resolve().parent.parent.parent / "static" / "Z-SIMHEI.TTF",
    Path("static/Z-SIMHEI.TTF"),
]
FONT_PATH = next((p for p in _FONT_DIRS if p.exists()), None)


class VideoComposerBase:
    """视频合成公共实现（快速/精铺模式共用）。"""

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

    def _parse_aspect(self, ratio: str, resolution: str) -> tuple[int, int]:
        short = {"480p": 480, "720p": 720, "1080p": 1080}[resolution]
        try:
            w, h = (int(p) for p in ratio.replace(":", "/").split("/"))
            r = w / h
        except (ValueError, ZeroDivisionError):
            return (short, int(short * 16 / 9))
        if r > 1:
            return (int(short * r), short)
        if r < 1:
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

        font_size = int(min(w, h) * 0.078)
        font = self._load_font(font_size)
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
