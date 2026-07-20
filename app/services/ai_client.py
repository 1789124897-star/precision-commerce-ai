"""大模型 API 客户端"""
import asyncio
import json
import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIClient:
    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {settings.API_KEY}",
            "Content-Type": "application/json",
        }

    async def analyze_product(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: list[str],
    ) -> str:
        """多模态分析：system_prompt + 用户提示词 + 图片 → 分析报告文本。"""
        content: list[dict[str, Any]] = []
        for url in image_data_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})
        content.append({"type": "text", "text": user_prompt})

        payload = {
            "model": settings.MULTIMODAL_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0.5,
        }
        data = await self._post(settings.BASE_URL, payload, timeout=180.0, headers=self._headers)
        content = data["choices"][0]["message"]["content"]
        if not content:
            raise ValueError("模型返回空内容")
        return content

    async def generate_strategy(self, *, prompt: str) -> dict[str, Any]:
        """纯文本推理：策略提示词 → JSON 策略结果。"""
        return await self._text_chat_to_json(
            system_content="你是一名资深电商策略师，只返回合法 JSON，输出必须使用简体中文。",
            user_content=prompt,
            temperature=0.6,
            max_tokens=8192,
        )

    async def generate_script(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """口播脚本生成：系统提示词 + 用户提示词 → JSON 脚本。"""
        return await self._text_chat_to_json(
            system_content=system_prompt,
            user_content=user_prompt,
            temperature=0.7,
            max_tokens=2048,
        )

    async def generate_shot_scenes(self, *, voiceovers: list[str]) -> list[str]:
        """根据每组口播文案生成镜头场景描述。"""
        from app.services.prompt_templates import build_shot_scene_prompt
        prompt = build_shot_scene_prompt(voiceovers)
        result = await self._text_chat_to_json(
            system_content="你是资深广告导演，专注电商短视频分镜设计，镜头描述精确到机位、焦段、运镜、布光。",
            user_content=prompt,
            temperature=0.6,
            max_tokens=2048,
        )
        scenes = result.get("scenes", [])
        if not scenes:
            raise ValueError(f"AI 镜头场景生成返回空 scenes: {result}")
        return scenes

    async def _text_chat_to_json(
        self,
        system_content: str,
        user_content: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """纯文本推理 → JSON：统一抽取内容 + 空值校验 + 反序列化。"""
        data = await self._text_chat(
            system_content=system_content,
            user_content=user_content,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = data["choices"][0]["message"].get("content", "")
        if not content or not content.strip():
            finish_reason = data["choices"][0].get("finish_reason", "unknown")
            raise ValueError(f"模型返回空内容，finish_reason={finish_reason}，请增大 max_tokens")
        return json.loads(content)

    async def _text_chat(
        self,
        system_content: str,
        user_content: str,
        temperature: float = 0.6,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        """纯文本推理统一入口。"""
        headers = {
            "Authorization": f"Bearer {settings.TEXT_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.TEXT_MODEL,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        t0 = time.monotonic()
        logger.info("DeepSeek 请求开始 model=%s max_tokens=%d", settings.TEXT_MODEL, max_tokens)
        result = await self._post(settings.TEXT_BASE_URL, payload, timeout=120.0, headers=headers)
        elapsed = time.monotonic() - t0
        logger.info("DeepSeek 请求完成 耗时=%.1fs", elapsed)
        return result

    async def _post(
        self,
        url: str,
        payload: dict[str, Any],
        timeout: float = 180.0,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """发送 POST 请求，网络瞬态错误自动重试 3 次。"""
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                    resp = await client.post(url, headers=headers or self._headers, json=payload)
                    resp.raise_for_status()
                    return resp.json()
            except (
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.ConnectError,
                httpx.RemoteProtocolError,
            ) as e:
                if attempt == 2:
                    raise
                wait = min(2 ** attempt, 8)
                logger.warning(
                    "HTTP 请求失败 (attempt %d/3, retry in %ds): %s",
                    attempt + 1, wait, type(e).__name__,
                )
                await asyncio.sleep(wait)

    async def generate_images(
        self,
        *,
        specs: list[dict[str, Any]],
        ref_image_data_urls: list[str] | None = None,
        size: str = "2048x2048",
    ) -> list[dict[str, Any]]:
        """并发生图：每张图按 spec 提示词生成，参考图可选，Semaphore 限流。

        spec.source='detail' 时自动使用 1440x2560 竖屏尺寸，
        其余使用参数 size（默认 2048x2048）。
        """
        semaphore = asyncio.Semaphore(settings.IMAGE_MAX_CONCURRENT)

        def _result(index: int, spec: dict[str, Any], url: str = "", error: str = "") -> dict[str, Any]:
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
                # 详情页自动使用竖屏尺寸
                img_size = "1440x2560" if spec.get("source") == "detail" else size
                try:
                    payload = {
                        "model": settings.SEEDREAM_IMAGE_MODEL,
                        "prompt": prompt,
                        "size": img_size,
                        "response_format": "url",
                        "stream": False,
                        "watermark": False,
                    }
                    if ref_image_data_urls:
                        payload["image"] = ref_image_data_urls  
                        payload["sequential_image_generation"] = "disabled"
                    logger.info(
                        "生图请求: model=%s, size=%s, prompt_len=%d, ref_images=%d",
                        payload["model"], payload["size"], len(prompt),
                        len(ref_image_data_urls) if ref_image_data_urls else 0,
                    )
                    data = await self._post(settings.SEEDREAM_IMAGE_URL, payload)
                    return _result(index, spec, url=data["data"][0]["url"])
                except httpx.HTTPStatusError as e:
                    logger.error("生图 API 返回错误: %d %s", e.response.status_code, e.response.text[:500])
                    return _result(index, spec, error=str(e))
                except Exception:
                    logger.exception("生图未预期异常, spec=%s", spec)
                    return _result(index, spec, error="internal error")

        tasks = [generate_one(i, spec) for i, spec in enumerate(specs)]
        return await asyncio.gather(*tasks)
