"""贪心分组器：短口播按 TTS 时长拼成 Seedance 镜头组（4s~12s）"""

import logging
from dataclasses import dataclass
from math import ceil

logger = logging.getLogger(__name__)

MIN_DUR = 4.0
MAX_DUR = 12.0


@dataclass
class ShotGroup:
    """一组口播对应一个 Seedance 镜头。"""
    voiceover: str
    duration_sec: float          # Seedance 视频时长（取整后）
    srt_duration_sec: float      # 实际口播时长
    merged_count: int
    first_frame_url: str = ""
    last_frame_url: str = ""
    scene_prompt: str = ""
    scene_prompt_en: str = ""


class ShotGrouper:
    """按 TTS 时长贪心累加，≥ 4s 封组。"""

    @staticmethod
    def group(texts: list[str], durations: list[float]) -> list[ShotGroup]:
        if not texts:
            raise ValueError("texts 为空")
        if len(texts) != len(durations):
            raise ValueError(
                f"texts 与 durations 长度不一致: {len(texts)} vs {len(durations)}"
            )

        groups: list[ShotGroup] = []
        buf_texts: list[str] = []
        buf_dur = 0.0

        for text, dur in zip(texts, durations):
            buf_texts.append(text)
            buf_dur += dur

            if buf_dur >= MIN_DUR:
                groups.append(_build_group(buf_texts, buf_dur))
                buf_texts, buf_dur = [], 0.0

        if buf_texts:
            if groups and groups[-1].srt_duration_sec + buf_dur <= MAX_DUR:
                _merge_tail(groups[-1], buf_texts, buf_dur)
            else:
                groups.append(_build_group(buf_texts, buf_dur))

        return groups


# ── helpers ──


def _build_group(texts: list[str], buf_dur: float) -> ShotGroup:
    video_dur = max(buf_dur, MIN_DUR)
    video_dur = ceil(video_dur)
    video_dur = min(video_dur, MAX_DUR)

    group = ShotGroup(
        voiceover="".join(texts),
        duration_sec=int(video_dur),
        srt_duration_sec=round(buf_dur, 1),
        merged_count=len(texts),
    )
    logger.info(f"封组: {len(texts)}段 TTS {buf_dur:.1f}s → {int(video_dur)}s")
    return group


def _merge_tail(group: ShotGroup, texts: list[str], dur: float) -> None:
    tts_total = group.srt_duration_sec + dur
    video_dur = max(tts_total, MIN_DUR)
    video_dur = ceil(video_dur)
    video_dur = min(video_dur, MAX_DUR)

    group.voiceover += "".join(texts)
    group.srt_duration_sec = round(tts_total, 1)
    group.duration_sec = int(video_dur)
    group.merged_count += len(texts)
