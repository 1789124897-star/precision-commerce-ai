"""TTS 语音合成 — edge-tts 逐字时间戳 + SRT 字幕生成"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import edge_tts
from aiohttp import ClientError
from edge_tts.exceptions import EdgeTTSException

from app.core.paths import AUDIO_DIR, to_output_url
from app.core.exceptions import AppException
from app.core.srt_utils import seconds_to_srt, srt_to_seconds
from app.services.ai_client import AIClient
from app.services.script_generator import ScriptGenerator

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+0%"

TICKS_PER_SEC = 10_000_000  # 微软时间戳单位：1秒 = 1000万 tick

_PUNCTUATION = {"。", "！", "？", "!", "?", "，", ",", "、", "：", "；", ".", "~", "～", "…"}


class TTSEngine:
    """edge-tts 合成：文本 → 音频 + 逐字字幕"""

    def __init__(self) -> None:
        os.environ.setdefault("NO_PROXY", "speech.platform.bing.com,*.bing.com")
        os.environ.setdefault("no_proxy", "speech.platform.bing.com,*.bing.com")

    # ── 合成入口 ──

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

        # 文本落盘
        ScriptGenerator.save_text(text=text, task_id=task_id)

        out_dir = AUDIO_DIR / task_id
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = out_dir / "voice.mp3"
        srt_path = out_dir / "subtitle.srt"

        # 流式合成：同时拿到音频字节 + 逐字时间戳
        result = await _synthesize_with_words(text=text, output_path=audio_path, voice=voice, rate=rate)

        # 逐字时间戳 → 按标点切句 → SRT
        _generate_srt_from_words(result["words"], srt_path)

        duration = result["offset_ticks"] / TICKS_PER_SEC

        # 解析 SRT 条目 → 贪心分组 → AI 生成镜头场景描述
        srt_entries = _parse_srt_entries(srt_path)
        logger.info(f"TTS SRT 条目数: {len(srt_entries)}, 总时长: {round(duration, 1)}s")

        grouped_shots = _group_srt_into_shots(srt_entries)
        logger.info(f"TTS 分组后镜头数: {len(grouped_shots)}")

        await _fill_scene_prompts(grouped_shots)

        return {
            "audio_path": to_output_url(audio_path),
            "srt_path": to_output_url(srt_path),
            "duration_sec": round(duration, 1),
            "grouped_shots": grouped_shots,
        }

    def run_sync(self, **kwargs: Any) -> dict:
        """同步包装，供 Celery 任务调用"""
        return asyncio.run(self.synthesize_from_text(**kwargs))


# ── 内部工具 ──


async def _fill_scene_prompts(grouped_shots: list[dict]) -> None:
    """用 AI 给每组镜头填场景描述，失败不阻断主流程"""
    voiceovers = [s["voiceover"] for s in grouped_shots]
    try:
        scene_prompts = await AIClient().generate_shot_scenes(voiceovers=voiceovers)
        for shot, sp in zip(grouped_shots, scene_prompts):
            shot["scene_prompt"] = sp.get("zh", "")      # 中文 → 前端显示
            shot["scene_prompt_en"] = sp.get("en", "")    # 英文 → Seedance
        logger.info(f"TTS 镜头场景描述生成完成: {len(scene_prompts)} 组")
    except Exception as e:
        logger.warning(f"TTS 镜头场景描述生成失败，使用空占位: {e}")
        for shot in grouped_shots:
            shot["scene_prompt"] = ""
            shot["scene_prompt_en"] = ""


async def _synthesize_with_words(text: str, output_path: Path, voice: str, rate: str, max_retries: int = 3) -> dict:
    """流式合成音频，返回逐字时间戳列表"""
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

            words: list[tuple[int, int, str]] = []
            for cue in submaker.cues:
                start_tick = int(cue.start.total_seconds() * TICKS_PER_SEC)
                end_tick = int(cue.end.total_seconds() * TICKS_PER_SEC)
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
                raise AppException("未获取到逐字时间戳")
            offset_ticks = words[-1][0] + words[-1][1]

            logger.info(
                f"TTS 完成（逐字）: {output_path} "
                f"({len(words)} 字, {offset_ticks / TICKS_PER_SEC:.1f}s)"
            )
            return {"words": words, "offset_ticks": offset_ticks}
        except (EdgeTTSException, ClientError, OSError, RuntimeError) as e:
            last_err = e
            wait = 2 ** attempt
            logger.warning(f"TTS 尝试 {attempt + 1}/{max_retries} 失败: {e}，{wait}s 后重试")
            await asyncio.sleep(wait)
    raise AppException(f"TTS 重试 {max_retries} 次均失败: {last_err}")


def _generate_srt_from_words(words: list[tuple[int, int, str]], output_path: Path,) -> None:
    """逐字时间戳 → 标点切句 → SRT

    标点强断，标点丢弃。18 字硬断。尾部 < 4 字并入上句。
    """
    MAX_CHARS = 18
    BREAK_CHARS = {"。", "！", "？", "!", "?", "，", ","}

    # 逐字扫描，按标点聚合成片段
    raw_chunks: list[dict] = []
    buf_words: list[tuple[int, int, str]] = []

    for offset, dur, char in words:
        buf_words.append((offset, dur, char))
        if char in BREAK_CHARS or len(buf_words) >= MAX_CHARS:
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
        start_sec = ch["start_tick"] / TICKS_PER_SEC
        end_sec = ch["end_tick"] / TICKS_PER_SEC
        lines.append(f"{i}")
        lines.append(f"{seconds_to_srt(start_sec)} --> {seconds_to_srt(end_sec)}")
        lines.append(ch["text"])
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"SRT 生成（逐字时间戳）: {output_path} ({len(merged)} 条)")


def _parse_srt_entries(srt_path: Path) -> list[dict]:
    """解析 SRT 文件，返回每条字幕的 {text, start_sec, end_sec, duration_sec}。"""
    if not srt_path.exists():
        raise AppException(f"SRT 文件不存在: {srt_path}", 404)

    raw = srt_path.read_text(encoding="utf-8").strip()
    entries: list[dict] = []
    for block in raw.split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        times = lines[1].split(" --> ")
        if len(times) != 2:
            continue
        start_sec = srt_to_seconds(times[0].strip())
        end_sec = srt_to_seconds(times[1].strip())
        text = "".join(lines[2:])
        entries.append({
            "text": text,
            "start_sec": round(start_sec, 3),
            "end_sec": round(end_sec, 3),
            "duration_sec": round(end_sec - start_sec, 3),
        })

    if not entries:
        raise AppException(f"SRT 解析结果为空: {srt_path}")
    return entries


def _group_srt_into_shots(srt_entries: list[dict]) -> list[dict]:
    """SRT 条目 → 镜头组，委托 ShotGrouper 统一分组逻辑。"""
    from app.services.shot_grouper import ShotGrouper

    # 过滤掉异常时长条目
    valid = [e for e in srt_entries if e.get("duration_sec", 0) > 0]
    if not valid:
        return []

    # 适配 ShotGrouper 输入格式
    shots = [{"voiceover": e["text"]} for e in valid]
    durations = [e["duration_sec"] for e in valid]

    shot_groups = ShotGrouper(min_dur=4.0, max_dur=12.0).group(shots, durations)

    # 映射回 TTS 需要的输出格式
    grouped: list[dict] = []
    for sg in shot_groups:
        voiceover = "".join(s.get("voiceover", "") for s in sg["shots"])
        grouped.append({
            "voiceover": voiceover,
            "duration_sec": sg["seedance_dur"],
            "srt_duration_sec": sg["tts_duration"],
            "merged_count": len(sg["shots"]),
            "image_url": "",
            "first_frame_url": "",
            "last_frame_url": "",
        })
    return grouped


def _flush_chunk(buf_words: list[tuple[int, int, str]]) -> dict:
    """缓冲区字戳压成一条字幕片段，去标点"""
    start = buf_words[0][0]
    last = buf_words[-1]
    end = last[0] + last[1]
    text = "".join(w[2] for w in buf_words if w[2] not in _PUNCTUATION)
    return {"start_tick": start, "end_tick": end, "text": text}
