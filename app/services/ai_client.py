"""LLM 统一入口：文本 / 多模态 / 生图（OpenAI 兼容协议）。"""

import asyncio
import logging
from typing import Any, Optional

from app.core.config import settings
from app.core.exceptions import AppException
from app.llm.base import BaseLLMClient, BaseMultimodalClient
from app.llm.factory import create_image_client, create_multimodal_client, create_text_client

logger = logging.getLogger(__name__)


class AIClient:
    """LLM 统一入口（文本 / 多模态 / 生图）。

    视频生成 → ShotService / VideoComposer
    语音合成 → TTSEngine
    """

    def __init__(self) -> None:
        self._text_client: BaseLLMClient = create_text_client()
        self._multimodal_client: BaseMultimodalClient = create_multimodal_client()

    # ==================================================================
    # 多模态分析 → 豆包
    # ==================================================================

    async def analyze_product(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: list[str],
        model: str = "",
    ) -> str:
        """多模态：商品图片 + 提示词 → 分析报告文本。model 空用 .env 配置。"""
        client = create_multimodal_client(model)
        return await client.analyze_multimodal(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image_data_urls=image_data_urls,
        )

    # ==================================================================
    # 纯文本推理 → DeepSeek
    # ==================================================================

    async def generate_strategy(self, *, prompt: str, model: str = "") -> dict[str, Any]:
        """策略提示词 → JSON 策略结果。model 空用 .env 配置。"""
        client = create_text_client(model)
        return await client.generate_json(
            system_prompt="你是一名资深电商策略师，只返回合法 JSON，输出必须使用简体中文。",
            user_prompt=prompt,
            temperature=0.6,
            max_tokens=8192,
        )

    async def generate_script(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """口播脚本：系统提示词 + 用户提示词 → JSON 脚本。"""
        return await self._text_client.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            max_tokens=2048,
        )

    async def generate_shot_scenes(self, *, voiceovers: list[str]) -> list[dict]:
        """每组口播文案 → 双语镜头场景描述。"""
        from app.services.prompts import build_shot_scene_prompt

        prompt = build_shot_scene_prompt(voiceovers)
        result = await self._text_client.generate_json(
            system_prompt=(
                "你是资深广告导演，专攻电商短视频 Seedance AI 分镜。"
                "你的描述必须极其详尽，每个镜头独一无二，禁止笼统和空洞。"
            ),
            user_prompt=prompt,
            temperature=0.7,
            max_tokens=8192,
        )
        scenes = result.get("scenes", [])
        if not scenes:
            raise AppException(f"AI 镜头场景生成返回空 scenes: {result}")
        normalized: list[dict] = []
        for s in scenes:
            if isinstance(s, str):
                normalized.append({"zh": s, "en": s})
            else:
                normalized.append({
                    "zh": s.get("zh", ""),
                    "en": s.get("en", s.get("zh", "")),
                })
        if len(normalized) != len(voiceovers):
            raise AppException(
                f"AI 场景描述数量不匹配: 期望 {len(voiceovers)} 组，实际 {len(normalized)} 组"
            )
        return normalized

    # 图片生成 → Seedream
    async def generate_images(
        self,
        *,
        specs: list[dict[str, Any]],
        ref_image_data_urls: Optional[list[str]] = None,
        size: str = "2048x2048",
        model: str = "",
    ) -> list[dict[str, Any]]:

        """并发生图，Semaphore 限流，按模型走 factory 客户端。"""
        semaphore = asyncio.Semaphore(settings.IMAGE_MAX_CONCURRENT)
        image_client = create_image_client(model or settings.GPT_IMAGE_MODEL)

        def _result(index: int, spec: dict[str, Any], url: str = "", error: str = "",) -> dict[str, Any]:
            return {
                "position": spec.get("position", index + 1),
                "type": spec.get("type", ""),
                "source": spec.get("source", ""),
                "prompt": spec.get("prompt", "").strip(),
                "url": url,
                "error": error,
            }

        async def generate_one(index: int, spec: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                prompt = spec.get("prompt", "").strip()
                if not prompt:
                    return _result(index, spec, error="prompt is empty")
                img_size = ("1440x2560" if spec.get("source") == "detail" else size)
                try:
                    url = await image_client.generate_image(
                        prompt=prompt,
                        size=img_size,
                        ref_image_data_urls=ref_image_data_urls or [],
                    )
                    return _result(index, spec, url=url)
                except AppException as e:
                    logger.error("生图失败 spec=%s: %s", spec, e.message)
                    return _result(index, spec, error=e.message)
                except Exception:
                    logger.exception("生图未预期异常, spec=%s", spec)
                    return _result(index, spec, error="internal error")

        tasks = [generate_one(i, spec) for i, spec in enumerate(specs)]
        return await asyncio.gather(*tasks)
