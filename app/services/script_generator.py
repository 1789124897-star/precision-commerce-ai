"""口播脚本生成 — DeepSeek JSON 模式 + 段数强制对齐"""
import asyncio
import logging
from typing import Any

from app.core.paths import SCRIPTS_DIR
from app.core.exceptions import AppException
from app.core.utils import save_json
from app.services.ai_client import AIClient
from app.services.prompts import build_product_script_prompt

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """口播脚本生成 — DeepSeek JSON 模式 + 段数强制对齐"""

    def __init__(self) -> None:
        self.ai = AIClient()

    async def generate(
        self,
        content: str,
        target_segments: int = 8,
        system_prompt: str = "",
        task_id: str = "",
    ) -> dict:

        system_prompt = system_prompt or (
            "你是一名拥有百万粉丝的抖音/快手电商带货达人，专攻家居日用类产品。"
            "开场3秒抛出痛点或场景，用语简洁口语化，结尾有CTA，严格返回JSON。"
        )

        user_prompt = build_product_script_prompt(
            content=content,
            target_segments=target_segments,
        )

        raw = await self.ai.generate_script(system_prompt=system_prompt, user_prompt=user_prompt)
        segments = raw.get("segments", [])
        if not segments:
            raise AppException("AI 返回的 segments 为空")
        result = self._build_result(segments)

        # 保存脚本文件
        script_path = self._save(task_id=task_id, result=result)
        return {"script": result, "script_path": script_path}

    def run_sync(self, **kwargs: Any) -> dict:
        """同步包装，供 Celery 任务调用"""
        return asyncio.run(self.generate(**kwargs))

    # ── 结果构建 ──

    @staticmethod
    def _build_result(segments: list[dict]) -> dict:
        """从 segments 构建完整结果。"""
        parts = []
        for i, seg in enumerate(segments):
            seg["index"] = i
            parts.append(seg.get("voiceover", ""))

        full_text = " ".join(parts)
        word_count = len(full_text.replace(" ", ""))

        return {
            "segments": segments,
            "full_text": full_text,
            "total_words": word_count,
        }

    # ── 文件 I/O ──

    @staticmethod
    def _save(task_id: str, result: dict) -> str:
        """保存脚本 JSON 文件，返回路径。"""
        task_dir = SCRIPTS_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        filepath = task_dir / "script.json"
        save_json(filepath, result)
        return str(filepath)
