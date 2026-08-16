"""TTS 语音合成 — edge-tts 句级时间戳 + SRT 字幕生成"""

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import edge_tts
from aiohttp import ClientError
from edge_tts.exceptions import EdgeTTSException

from app.core.exceptions import AppException
from app.core.paths import AUDIO_DIR, to_output_url
from app.core.srt_utils import seconds_to_srt
from app.services.ai_client import AIClient
from app.services.shot_grouper import ShotGroup, ShotGrouper

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+0%"

TICKS_PER_SEC = 10_000_000  # 微软时间戳单位：1秒 = 1000万 tick

_PUNCTUATION = {"。", "！", "？", "!", "?", "，", ",", "、", "：", "；", ".", "~", "～", "…"}


# ── 流水线数据结构──
#
#  SentenceBoundary → TimedWord → SynthesizeResult → _SubtitleChunk
#     1.edge-tts       2.逐字       3.打包返回         4.断句+合并


@dataclass
class SentenceBoundary:
    """1. edge-tts 原始句级时间戳
    SentenceBoundary(offset=1000000, duration=52000000, text="这个水杯保温效果特别好，值得入手。")
    """
    offset: int
    duration: int
    text: str


@dataclass
class TimedWord:
    """2. 逐字时间戳，从 SentenceBoundary 均分得到
    TimedWord(start_tick=1000000, dur_tick=4727272, char="这")
    TimedWord(start_tick=5727272, dur_tick=4727272, char="个")
    """
    start_tick: int
    dur_tick: int
    char: str


@dataclass
class SynthesizeResult:
    """3. _synthesize_with_words 返回：全部逐字时间戳 + 音频总长
    SynthesizeResult(
        words=[
            TimedWord(start_tick=1000000, dur_tick=4727272, char="这"),
            TimedWord(start_tick=5727272, dur_tick=4727272, char="个"),
            ...
        ],
        end_ticks=53000000,
    )
    """
    words: list[TimedWord]
    end_ticks: int


@dataclass
class _SubtitleChunk:
    """4. 按标点断句 + 逗号合并后的字幕片段（tick 精度）
    _SubtitleChunk(start_tick=1000000, end_tick=43000000, text="这个水杯保温效果特别好", break_char="，")
    _SubtitleChunk(start_tick=43000000, end_tick=53000000, text="值得入手", break_char="。")
    """
    start_tick: int
    end_tick: int
    text: str
    break_char: Optional[str] = None


class TTSEngine:
    """edge-tts 合成：文本 → 音频 + 逐字字幕"""

    def __init__(self) -> None:
        os.environ.setdefault("NO_PROXY", "speech.platform.bing.com,*.bing.com")
        os.environ.setdefault("no_proxy", "speech.platform.bing.com,*.bing.com")

    async def synthesize_from_text(
        self,
        text: str,
        voice: str = "",
        rate: str = "",
        task_id: str = "",
    ) -> dict:
        """文本 → 音频 + SRT + 镜头分组"""
        text = text.strip()
        voice = voice or DEFAULT_VOICE
        rate = rate or DEFAULT_RATE

        # 输出目录
        audio_dir = AUDIO_DIR / task_id
        audio_dir.mkdir(parents=True, exist_ok=True)
        script_path = audio_dir / "script.txt"
        script_path.write_text(text, encoding="utf-8")

        audio_path = audio_dir / "voice.mp3"
        srt_path = audio_dir / "subtitle.srt"
        raw_chunks_path = audio_dir / "voice.raw_chunks.json"

        # 1. 流式合成：拿到音频字节 + 句级时间戳
        result = await _synthesize_with_words(
            text=text,
            output_path=audio_path,
            raw_chunks_path=raw_chunks_path,
            voice=voice,
            rate=rate,
        )

        # 2. 句级时间戳 → 均分到字 → 按标点切句 → 逗号合并 → 写 SRT
        texts, durations = _build_srt(result.words, srt_path)
        duration = result.end_ticks / TICKS_PER_SEC
        logger.info(f"TTS SRT 条目数: {len(texts)}, 总时长: {round(duration, 1)}s")

        # 3. 贪心分组
        grouped_shots = ShotGrouper.group(texts, durations)
        logger.info(f"TTS 分组后镜头数: {len(grouped_shots)}")

        # 4. AI 生成场景描述
        await _fill_scene_prompts(grouped_shots)

        return {
            "audio_path": to_output_url(audio_path),
            "srt_path": to_output_url(srt_path),
            "duration_sec": round(duration, 1),
            "grouped_shots": [asdict(g) for g in grouped_shots],
        }

    def run_sync(self, **kwargs: Any) -> dict:
        """同步包装，供 Celery 任务调用"""
        return asyncio.run(self.synthesize_from_text(**kwargs))


# ── 内部工具 ──


async def _fill_scene_prompts(groups: list[ShotGroup]) -> None:
    """用 AI 给每组镜头填场景描述，失败不阻断主流程"""
    voiceovers = [s.voiceover for s in groups]
    try:
        scene_prompts = await AIClient().generate_shot_scenes(voiceovers=voiceovers)
        for shot, sp in zip(groups, scene_prompts):
            shot.scene_prompt = sp.get("zh", "")
            shot.scene_prompt_en = sp.get("en", "")
        logger.info(f"TTS 镜头场景描述生成完成: {len(scene_prompts)} 组")
    except (AppException, ValueError, KeyError, ConnectionError, TimeoutError) as e:
        logger.warning(f"TTS 镜头场景描述生成失败，使用空占位: {e}")
        for shot in groups:
            shot.scene_prompt = ""
            shot.scene_prompt_en = ""


async def _synthesize_with_words(
    text: str,
    output_path: Path,
    raw_chunks_path: Path,
    voice: str,
    rate: str,
    max_retries: int = 3,
) -> SynthesizeResult:
    """流式合成音频，返回逐字时间戳 + 音频总 tick。"""
    last_err = None
    for attempt in range(max_retries):
        try:
            comm = edge_tts.Communicate(text=text, voice=voice, rate=rate)
            audio_bytes = bytearray()
            boundaries: list[SentenceBoundary] = []

            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    audio_bytes.extend(chunk["data"])
                elif chunk["type"] == "SentenceBoundary":
                    boundaries.append(SentenceBoundary(
                        offset=int(chunk["offset"]),
                        duration=int(chunk["duration"]),
                        text=chunk["text"],
                    ))

            if not audio_bytes:
                raise AppException("TTS 未返回音频数据")
            if not boundaries:
                raise AppException("TTS 未返回 SentenceBoundary 时间戳")

            output_path.write_bytes(audio_bytes)
            raw_chunks_path.write_text(
                json.dumps([{
                    "type": "SentenceBoundary",
                    "offset": b.offset,
                    "duration": b.duration,
                    "text": b.text,
                    "offset_sec": b.offset / TICKS_PER_SEC,
                    "duration_sec": b.duration / TICKS_PER_SEC,
                } for b in boundaries], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            words: list[TimedWord] = []
            for seg in boundaries:
                chars = list(seg.text)
                if not chars:
                    continue
                per_char_dur = seg.duration / len(chars)
                for i, ch in enumerate(chars):
                    char_start = int(seg.offset + i * per_char_dur)
                    char_dur = int(seg.offset + seg.duration - char_start) if i == len(chars) - 1 else int(per_char_dur)
                    words.append(TimedWord(start_tick=char_start, dur_tick=max(char_dur, 1), char=ch))

            end_ticks = words[-1].start_tick + words[-1].dur_tick

            logger.info(
                f"TTS 完成: {output_path} "
                f"({len(boundaries)} 句, {len(words)} 字, {end_ticks / TICKS_PER_SEC:.1f}s)"
            )
            return SynthesizeResult(words=words, end_ticks=end_ticks)
        except (EdgeTTSException, ClientError, OSError, RuntimeError) as e:
            last_err = e
            wait = 2 ** attempt
            logger.warning(f"TTS 尝试 {attempt + 1}/{max_retries} 失败: {e}，{wait}s 后重试")
            await asyncio.sleep(wait)
    raise AppException(f"TTS 重试 {max_retries} 次均失败: {last_err}")


def _build_srt(words: list[TimedWord], output_path: Path) -> tuple[list[str], list[float]]:
    """逐字时间戳 → 写 SRT 文件，返回 (texts, durations) 供分组用。"""
    MAX_CHARS = 12
    CLOSED_BREAKS = {"。", "！", "？", "!", "?"}
    OPEN_BREAKS = {"，", ","}
    BREAKS = CLOSED_BREAKS | OPEN_BREAKS

    # 第一轮：按标点 + 12字限断句
    raw_chunks: list[_SubtitleChunk] = []
    buf_words: list[TimedWord] = []

    for w in words:
        buf_words.append(w)
        stripped = sum(1 for x in buf_words if x.char not in _PUNCTUATION)
        if w.char in BREAKS or stripped >= MAX_CHARS:
            break_char = w.char if w.char in BREAKS else None
            raw_chunks.append(_flush_chunk(buf_words, break_char))
            buf_words = []

    if buf_words:
        raw_chunks.append(_flush_chunk(buf_words, None))

    # 第二轮：逗号结尾的片段向前合并
    merged: list[_SubtitleChunk] = []
    for ch in raw_chunks:
        if (
            merged
            and ch.break_char in OPEN_BREAKS
            and merged[-1].break_char not in CLOSED_BREAKS
            and len(merged[-1].text) + len(ch.text) <= MAX_CHARS
        ):
            merged[-1].end_tick = ch.end_tick
            merged[-1].text += ch.text
            merged[-1].break_char = ch.break_char
        else:
            merged.append(ch)

    # 写 SRT + 构建返回值
    srt_lines: list[str] = []
    texts: list[str] = []
    durations: list[float] = []

    for i, ch in enumerate(merged, 1):
        if not ch.text:
            continue
        start_sec = ch.start_tick / TICKS_PER_SEC
        end_sec = ch.end_tick / TICKS_PER_SEC
        srt_lines.append(f"{i}")
        srt_lines.append(f"{seconds_to_srt(start_sec)} --> {seconds_to_srt(end_sec)}")
        srt_lines.append(ch.text)
        srt_lines.append("")
        texts.append(ch.text)
        durations.append(round(end_sec - start_sec, 3))

    output_path.write_text("\n".join(srt_lines), encoding="utf-8")
    logger.info(f"SRT 生成: {output_path} ({len(texts)} 条)")
    return texts, durations


def _flush_chunk(buf_words: list[TimedWord], break_char: Optional[str]) -> _SubtitleChunk:
    """缓冲区字戳压成一条字幕片段，去标点，记录触发标点类型。"""
    start = buf_words[0].start_tick
    last = buf_words[-1]
    end = last.start_tick + last.dur_tick
    text = "".join(w.char for w in buf_words if w.char not in _PUNCTUATION)
    return _SubtitleChunk(start_tick=start, end_tick=end, text=text, break_char=break_char)
