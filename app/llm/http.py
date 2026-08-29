"""共享 HTTP 客户端——带退避重试的 POST 请求，所有 LLM 提供者复用。"""
import asyncio
import logging
from typing import Any, Optional, cast

import httpx

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


async def post_with_retry(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout: float = 180.0,
    max_retries: int = 3,
    proxy: Optional[str] = None,
    files: Optional[list[Any]] = None,
) -> dict[str, Any]:
    """POST 请求，网络瞬态错误指数退避重试。files 非空时走 multipart/form-data。"""
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False, proxy=proxy, follow_redirects=True) as client:
                if files:
                    resp = await client.post(url, headers=headers, data=payload, files=files)
                else:
                    resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 500 or resp.status_code == 429:
                    resp.raise_for_status()  
                if resp.status_code >= 400:
                    raise AppException(f"API 返回 {resp.status_code}: {resp.text[:200]}", resp.status_code)
                return cast("dict[str, Any]", resp.json())
        except (
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
        ) as e:
            if attempt == max_retries - 1:
                raise
            wait = min(2 ** attempt, 8)
            logger.warning(
                "HTTP 请求失败 (attempt %d/%d, retry in %ds): %s",
                attempt + 1, max_retries, wait, type(e).__name__,
            )
            await asyncio.sleep(wait)
    raise AppException("HTTP 请求失败，已达最大重试次数", 502)
