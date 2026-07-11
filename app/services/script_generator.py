"""口播脚本生成 — DeepSeek JSON 模式 + 段数强制对齐"""
import json
import logging
from pathlib import Path

from app.core.paths import SCRIPT_DIR as SCRIPTS_DIR
from app.services.ai_client import AIClient
from app.services.prompt_templates import build_product_script_prompt

logger = logging.getLogger(__name__)


class ScriptGenerator:
    def __init__(self):
        self.ai = AIClient()

    async def generate(
        self,
        content: str,
        target_segments: int = 8,
        system_prompt: str = "",
    ) -> dict:
        """生成结构化口播脚本（段数强制对齐）。

        Returns:
            {"script": {...}, "script_path": "..."}
        """
        actual_system = system_prompt.strip() if system_prompt else (
            "你是一名拥有百万粉丝的抖音/快手电商带货达人，专攻家居日用类产品。"
            "开场3秒抛出痛点或场景，用语简洁口语化，结尾有CTA，严格返回JSON。"
        )

        user_prompt = build_product_script_prompt(
            content=content,
            target_segments=target_segments,
        )

        raw = await self.ai.generate_script(system_prompt=actual_system, user_prompt=user_prompt)
        segments = raw.get("segments", [])
        if not segments:
            raise ValueError("AI 返回的 segments 为空")
        result = self._build_result(segments)

        # 保存脚本文件
        script_path = self._save(task_id="script", result=result)
        return {"script": result, "script_path": script_path}

    # ── 结果构建 ──

    @staticmethod
    def _build_result(segments: list[dict]) -> dict:
        """从 segments 构建完整结果。"""
        for i, seg in enumerate(segments):
            seg["index"] = i
            text = seg.get("voiceover", "")
            seg["estimated_duration"] = round(max(1.8, len(text.replace(" ", "")) * 0.28), 1)
            if "image_keywords" not in seg:
                seg["image_keywords"] = ["产品"]

        full_text = " ".join(s["voiceover"] for s in segments)
        total_dur = round(sum(s["estimated_duration"] for s in segments), 1)
        word_count = len(full_text.replace(" ", ""))

        return {
            "segments": segments,
            "full_text": full_text,
            "total_words": word_count,
            "estimated_duration": total_dur,
        }

    # ── 文件 I/O ──

    @staticmethod
    def _save(task_id: str, result: dict) -> str:
        """保存脚本 JSON 文件，返回路径。"""
        task_dir = SCRIPTS_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        filepath = task_dir / "script.json"
        filepath.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(filepath)

    @staticmethod
    def save_text(text: str, task_id: str) -> str:
        """保存纯文本脚本，返回路径。"""
        task_dir = SCRIPTS_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        filepath = task_dir / "script.txt"
        filepath.write_text(text, encoding="utf-8")
        return str(filepath)
