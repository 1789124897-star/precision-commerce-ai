"""产品分析服务"""
import asyncio
import logging
import time
from typing import Any

from app.core.utils import image_to_data_url
from app.services.ai_client import AIClient
from app.services.prompts import STRATEGY_TYPES, build_analysis_prompt, build_strategy_prompt

logger = logging.getLogger(__name__)


class AnalysisService:
    """产品分析 + 策略生成服务"""

    def __init__(self):
        self.ai = AIClient()

    async def run(
        self,
        name: str,
        function: str,
        price: str,
        extra: str = "",
        custom_prompt: str = "",
        image_paths: list[str] | None = None,
    ) -> dict:
        """产品分析 → 返回 {"analysis": str, "product_name": str}"""
        image_data_urls = [image_to_data_url(url) for url in image_paths] if image_paths else []

        user_prompt = build_analysis_prompt(name, function, price, extra, custom_prompt)
        analysis_text = await self.ai.analyze_product(
            system_prompt="你是一名资深电商分析师，请从商品视觉与文本中提炼用户需求、卖点与营销方向。",
            user_prompt=user_prompt,
            image_data_urls=image_data_urls,
        )
        return {"analysis": analysis_text, "product_name": name}

    def run_sync(self, **kwargs: Any) -> dict:
        """同步包装，供 Celery 任务调用"""
        return asyncio.run(self.run(**kwargs))

    async def run_strategies(self, analysis: str, system_prompt: str = "") -> dict:
        """并发调用 3 套策略，返回 {"strategies": {type: text}}"""
        client = AIClient()
        coroutines = []
        for code, meta in STRATEGY_TYPES.items():
            prompt = build_strategy_prompt(analysis, code, meta["name"], system_prompt)
            coroutines.append(client.generate_strategy(prompt=prompt))
        t0 = time.monotonic()
        logger.info("策略生成开始，并发数=%d", len(coroutines))
        results = await asyncio.gather(*coroutines)
        elapsed = time.monotonic() - t0
        logger.info("策略生成完成，总耗时=%.1fs，平均=%.1fs/套", elapsed, elapsed / len(coroutines))
        return {"strategies": dict(zip(STRATEGY_TYPES.keys(), results))}

    def run_strategies_sync(self, **kwargs: Any) -> dict:
        """同步包装，供 Celery 任务调用"""
        return asyncio.run(self.run_strategies(
            analysis=kwargs.get("analysis", ""),
            system_prompt=kwargs.get("system_prompt", ""),
        ))
