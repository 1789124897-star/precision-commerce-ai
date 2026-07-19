"""镜头组分组器 — 解决 Seedance 4s 底限与短口播的冲突

核心逻辑：
- 一段口播 < 4s 时不自成一个镜头，而是跟相邻段拼到一起
- 拼到 TTS 总时长 ≥ 4s 时封组，生成一个 Seedance 视频
- Seedance 时长取 ceil(tts_total)，保证画面不会比音频短
- 组内多段时使用首尾帧模式（第一段的图 → 最后一端的图）
"""

import logging
from math import ceil

logger = logging.getLogger(__name__)

MIN_DUR = 4.0   # Seedance 最短支持
MAX_DUR = 12.0  # Seedance 最长支持


class ShotGrouper:
    """将原始分镜按实际 TTS 时长合并为镜头组。"""

    def __init__(self, min_dur: float = MIN_DUR, max_dur: float = MAX_DUR):
        self.min_dur = min_dur
        self.max_dur = max_dur

    def group(self, shots: list[dict], segment_durations: list[float]) -> list[dict]:
        """贪心分组：从左到右累加 TTS 时长，≥ min_dur 时封组。

        Args:
            shots: 原始分镜列表，每个 dict 含 image_url/first_frame_url/last_frame_url/scene_prompt 等
            segment_durations: 每段口播的实际 TTS 时长（秒），与 shots 一一对应

        Returns:
            shot_groups: 分组后的镜头组列表，每组可直接喂给 compose_premium 的单次 Seedance 调用
              [{
                  "shots": [原始shot, ...],       # 该组包含的原始分镜
                  "tts_duration": 5.4,           # 组内 TTS 总时长
                  "seedance_dur": 6,             # ceil 后的整数秒，保证 ≥4
                  "first_frame_url": "...",       # 首帧 = 第一个 shot 的图
                  "last_frame_url": "...",        # 尾帧 = 最后一个 shot 的图（单段时为 ""）
                  "scene_prompt": "...",          # 合并后的场景描述
                  "image_url": "...",             # 单段时直接用
                  "mode": "first_last" | "single", # 首尾帧模式还是单图模式
              }, ...]
        """
        if not shots or not segment_durations:
            logger.warning("ShotGrouper: 输入为空，返回空列表")
            return []

        assert len(shots) == len(segment_durations), \
            f"shots({len(shots)}) 与 segment_durations({len(segment_durations)}) 长度不一致"

        groups: list[dict] = []
        buf_shots: list[dict] = []
        buf_dur = 0.0

        def seal_group():
            """封组：将缓冲区中的分镜打包为一个镜头组。"""
            if not buf_shots:
                return

            tts_total = buf_dur
            # ceil 取整 → 画面永远不比音频短
            seedance_dur = int(ceil(max(tts_total, self.min_dur)))
            # 但不超过 max_dur
            seedance_dur = min(seedance_dur, int(self.max_dur))

            first = buf_shots[0]
            last = buf_shots[-1]

            # 组内只有一段 → 单图模式
            if len(buf_shots) == 1:
                groups.append({
                    "shots": list(buf_shots),
                    "tts_duration": round(tts_total, 1),
                    "seedance_dur": seedance_dur,
                    "image_url": first.get("image_url", ""),
                    "first_frame_url": first.get("first_frame_url", "") or first.get("image_url", ""),
                    "last_frame_url": "",
                    "scene_prompt": first.get("scene_prompt", ""),
                    "mode": "single",
                })
            else:
                # 多段 → 首尾帧模式
                first_url = first.get("first_frame_url", "") or first.get("image_url", "")
                last_url = last.get("last_frame_url", "") or last.get("image_url", "")
                merged_prompt = " | ".join(
                    s.get("scene_prompt", "") for s in buf_shots if s.get("scene_prompt")
                ) or "smooth transition, professional product showcase"

                groups.append({
                    "shots": list(buf_shots),
                    "tts_duration": round(tts_total, 1),
                    "seedance_dur": seedance_dur,
                    "image_url": "",
                    "first_frame_url": first_url,
                    "last_frame_url": last_url,
                    "scene_prompt": merged_prompt,
                    "mode": "first_last",
                })

            logger.info(
                f"镜头组封组: {len(buf_shots)} 段口播, "
                f"TTS {tts_total:.1f}s → Seedance {seedance_dur}s "
                f"(mode={groups[-1]['mode']})"
            )

        for i, (shot, dur) in enumerate(zip(shots, segment_durations)):
            # 如果当前段本身就 ≥ max_dur，先封之前的组再单独成组
            if dur >= self.max_dur:
                seal_group()
                buf_shots = [shot]
                buf_dur = dur
                # 长段需要拆分：这里简单处理，截断到 max_dur
                # 更精细的拆分可后续扩展
                seal_group()
                buf_shots = []
                buf_dur = 0.0
                continue

            # 如果加入当前段会超 max_dur，先封组再开新组
            if buf_dur + dur > self.max_dur and buf_dur >= self.min_dur:
                seal_group()
                buf_shots = []
                buf_dur = 0.0

            buf_shots.append(shot)
            buf_dur += dur

            # 累计 ≥ min_dur → 封组
            if buf_dur >= self.min_dur:
                # 如果下一段加上去不超 max_dur，可以等一等
                # 但如果下一段加上去正好凑整，可以贪一下
                # 简单策略：≥ min_dur 就封，保持节奏
                seal_group()
                buf_shots = []
                buf_dur = 0.0

        # 尾部残留：强制封组（扩展到 min_dur）
        if buf_shots:
            seal_group()

        return groups
