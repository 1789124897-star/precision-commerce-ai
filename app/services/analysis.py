"""产品分析服务"""
import asyncio
from typing import Any, Optional

from app.core.utils import image_to_data_url
from app.services.prompts import STRATEGY_TYPES, build_analysis_prompt, build_strategy_prompt
from app.services.ai_client import AIClient


async def run_analysis(
    name: str,
    function: str,
    price: str,
    extra: str = "",
    custom_prompt: str = "",
    image_paths: Optional[list[str]] = None,
) -> str:
    image_data_urls = [image_to_data_url(url) for url in image_paths] if image_paths else []

    user_prompt = build_analysis_prompt(name, function, price, extra, custom_prompt)
    return await AIClient().analyze_product(
        system_prompt="你是一名资深电商分析师，请从商品视觉与文本中提炼用户需求、卖点与营销方向。",
        user_prompt=user_prompt,
        image_data_urls=image_data_urls,
    )


def run_analysis_sync(**kwargs: Any) -> dict:
    """同步包装，供 Celery 任务调用"""
    analysis_text = asyncio.run(run_analysis(**kwargs))
    return {"analysis": analysis_text, "product_name": kwargs.get("name", "")}


async def run_strategies(analysis: str, system_prompt: str = "") -> dict:
    """并发调用 3 套策略，返回结果字典"""
    client = AIClient()
    coroutines = []
    for code, meta in STRATEGY_TYPES.items():
        prompt = build_strategy_prompt(analysis, code, meta["name"], system_prompt)
        coroutines.append(client.generate_strategy(prompt=prompt))
    results = await asyncio.gather(*coroutines)
    return {"strategies": dict(zip(STRATEGY_TYPES.keys(), results))}


def run_strategies_sync(**kwargs: Any) -> dict:
    """同步包装，供 Celery 任务调用"""
    return asyncio.run(run_strategies(
        analysis=kwargs.get("analysis", ""),
        system_prompt=kwargs.get("system_prompt", ""),
    ))
