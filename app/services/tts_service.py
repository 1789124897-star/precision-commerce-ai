"""TTS 语音合成 — edge-tts 逐字时间戳 + SRT 字幕生成"""

import os
os.environ["NO_PROXY"] = "speech.platform.bing.com,*.bing.com"
os.environ["no_proxy"] = "speech.platform.bing.com,*.bing.com"
import asyncio
import json
import logging
import uuid
from pathlib import Path

import edge_tts

from app.core.paths import AUDIO_DIR
from app.services.script_generator import ScriptGenerator

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+0%"


class TTSEngine:
    """edge-tts 语音合成引擎，全量脚本合成 + 逐字时间戳 SRT。"""

    # ── 全量合成 ──

    @staticmethod
    async def synthesize_from_script(
        script_path: str = "",
        text: str = "",
        voice: str = "",
        rate: str = "",
        task_id: str = "",
    ) -> dict:
        """从脚本 JSON 或纯文本合成音频 + SRT。

        text 非空且无 script_path 时自动落盘。
        Returns:
            {audio_path, srt_path, duration_sec}
        """
        v = voice or DEFAULT_VOICE
        r = rate or DEFAULT_RATE

        if text and not script_path:
            task_id = task_id or uuid.uuid4().hex[:8]
            script_path = ScriptGenerator.save_text(text=text, task_id=task_id)

        script_file = Path(script_path)
        if not script_file.exists():
            raise FileNotFoundError(f"脚本文件不存在: {script_path}")

        raw = script_file.read_text(encoding="utf-8").strip()
        # 兼容 JSON 脚本和纯文本
        try:
            script = json.loads(raw)
            full_text = script.get("full_text", "")
        except (json.JSONDecodeError, ValueError):
            full_text = raw
        if not full_text:
            raise ValueError("脚本内容为空")

        task_id = script_file.parent.name
        out_dir = AUDIO_DIR / task_id
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = out_dir / "voice.mp3"
        srt_path = out_dir / "subtitle.srt"

        # 流式合成：同时拿到音频字节 + 逐字时间戳
        result = await _synthesize_with_words(full_text, audio_path, voice=v, rate=r)

        # 逐字时间戳 → 按标点切句 → SRT
        _generate_srt_from_words(result["words"], result["offset_ticks"], srt_path)

        duration = result["offset_ticks"] / 10_000_000  # ticks → 秒

        return {
            "audio_path": "/" + str(audio_path).replace("\\", "/"),
            "srt_path": "/" + str(srt_path).replace("\\", "/"),
            "duration_sec": round(duration, 1),
        }


# ── 内部工具 ──


async def _synthesize_with_words(
    text: str, output_path: Path, voice: str, rate: str, max_retries: int = 3,
) -> dict:
    """流式合成，返回 {words: [(offset_ticks, duration_ticks, char), ...], offset_ticks: int}"""
    last_err = None
    for attempt in range(max_retries):
        try:
            comm = edge_tts.Communicate(text=text, voice=voice, rate=rate)
            submaker = edge_tts.SubMaker()
            audio_bytes = bytearray()

            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    audio_bytes.extend(chunk["data"])
                elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                    submaker.feed(chunk)

            output_path.write_bytes(audio_bytes)

            # SubMaker.cues 中存的是 Subtitle 对象（.start/.end 为 timedelta，.content 为文本）
            words: list[tuple[int, int, str]] = []
            for cue in submaker.cues:
                start_tick = int(cue.start.total_seconds() * 10_000_000)
                end_tick = int(cue.end.total_seconds() * 10_000_000)
                dur_tick = end_tick - start_tick
                chars = list(cue.content)
                if not chars:
                    continue
                per_char_dur = dur_tick / len(chars)
                for i, ch in enumerate(chars):
                    char_start = int(start_tick + i * per_char_dur)
                    char_dur = int(end_tick - char_start) if i == len(chars) - 1 else int(per_char_dur)
                    words.append((char_start, max(char_dur, 1), ch))

            if not words:
                # 没有任何时间戳 → 按口语速度估算
                rate_num = float(rate.replace("%", "").replace("+", "").replace("default", "0")) if rate else 0
                factor = 1.0 + rate_num / 100  # rate="+20%" → 1.2× 速度
                chars_per_sec = 3.5 * factor
                total_dur = max(1.0, len(text) / max(chars_per_sec, 1.0))
                offset_ticks = int(total_dur * 10_000_000)
                per_char_ticks = offset_ticks // max(len(text), 1)
                words = [(i * per_char_ticks, per_char_ticks, ch) for i, ch in enumerate(text)]
                logger.warning(
                    f"TTS 无逐字时间戳，估算时长: {total_dur:.1f}s "
                    f"(rate={rate}, {len(text)} 字)"
                )
            else:
                offset_ticks = words[-1][0] + words[-1][1]

            logger.info(
                f"TTS 完成（逐字）: {output_path} "
                f"({len(words)} 字, {offset_ticks / 10_000_000:.1f}s)"
            )
            return {"words": words, "offset_ticks": offset_ticks}
        except Exception as e:
            last_err = e
            wait = 2 ** attempt
            logger.warning(f"TTS 尝试 {attempt + 1}/{max_retries} 失败: {e}，{wait}s 后重试")
            await asyncio.sleep(wait)
    raise RuntimeError(f"TTS 重试 {max_retries} 次均失败: {last_err}")


def _generate_srt_from_words(
    words: list[tuple[int, int, str]],
    total_ticks: int,
    output_path: Path,
) -> Path:
    """逐字时间戳 + 标点驱动切句 → SRT（字幕不含标点）。

    规则：
    - 句号/感叹号/问号 → 强断，标点丢弃
    - 逗号 → 强断，标点丢弃
    - 长度达到 18 字 → 硬断
    - 尾部残留 < 4 字 → 并入上一句
    """
    MAX_CHARS = 18
    BREAK_CHARS = {"。", "！", "？", "!", "?", "，", ","}

    # 逐字扫描，按标点聚合成片段
    raw_chunks: list[dict] = []
    buf_words: list[tuple[int, int, str]] = []

    for offset, dur, char in words:
        buf_words.append((offset, dur, char))
        if char in BREAK_CHARS:
            raw_chunks.append(_flush_chunk(buf_words))
            buf_words = []
        elif len(buf_words) >= MAX_CHARS:
            raw_chunks.append(_flush_chunk(buf_words))
            buf_words = []

    if buf_words:
        raw_chunks.append(_flush_chunk(buf_words))

    # 合并过短尾部到上一句
    merged: list[dict] = []
    for ch in raw_chunks:
        if merged and len(ch["text"]) < 4:
            merged[-1]["end_tick"] = ch["end_tick"]
            merged[-1]["text"] += ch["text"]
        else:
            merged.append(ch)

    # 写 SRT
    lines: list[str] = []
    for i, ch in enumerate(merged, 1):
        start_sec = ch["start_tick"] / 10_000_000
        end_sec = ch["end_tick"] / 10_000_000
        lines.append(f"{i}")
        lines.append(f"{_secs_to_srt(start_sec)} --> {_secs_to_srt(end_sec)}")
        lines.append(ch["text"])
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"SRT 生成（逐字时间戳）: {output_path} ({len(merged)} 条)")
    return output_path


_PUNCTUATION = {"。", "！", "？", "!", "?", "，", ",", "、", "：", "；", ".", "~", "～", "…"}


def _flush_chunk(buf_words: list[tuple[int, int, str]]) -> dict:
    start = buf_words[0][0]
    last = buf_words[-1]
    end = last[0] + last[1]
    text = "".join(w[2] for w in buf_words if w[2] not in _PUNCTUATION)
    return {"start_tick": start, "end_tick": end, "text": text}


def _secs_to_srt(secs: float) -> str:
    """秒 → SRT 时间格式 HH:MM:SS,mmm"""
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    ms = int((secs - int(secs)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
