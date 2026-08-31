"""LLM 抽象基类"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional


class BaseLLMClient(ABC):
    """纯文本 LLM 客户端"""

    @abstractmethod
    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        """发送提示词，返回已解析的 JSON dict。"""
        ...


class BaseMultimodalClient(ABC):
    """多模态客户端"""

    @abstractmethod
    async def analyze_multimodal(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: list[str],
    ) -> str:
        """传入图片 data URL + 提示词，返回分析文本。"""
        ...


class BaseImageClient(ABC):
    """生图客户端"""

    @abstractmethod
    async def generate_image(
        self,
        *,
        prompt: str,
        size: str,
        ref_image_data_urls: list[str],
    ) -> str:
        """单张生图。"""
        ...


class BaseVideoClient(ABC):
    """视频生成客户端：分镜/图生/首尾帧/文生统一契约。

    实现类：SeedanceService（火山方舟）、ApimartSeedanceClient（APIMart 中转）。
    """

    @abstractmethod
    def generate_shot_sync(self, **kwargs: Any) -> Path:
        """同步生成单个分镜（Celery 任务入口）。"""
        ...

    @abstractmethod
    async def generate_clip_from_url(
        self,
        image_url: str,
        prompt: str,
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        shot_index: int = 0,
        on_progress: Optional[Callable] = None,
        generate_audio: bool = False,
        resolution: str = "720p",
    ) -> Path:
        """图生视频-首帧：仅一张起始图。"""
        ...

    @abstractmethod
    async def generate_clip_first_last_frame(
        self,
        first_frame_url: str,
        last_frame_url: str,
        prompt: str,
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        shot_index: int = 0,
        on_progress: Optional[Callable] = None,
        generate_audio: bool = False,
        resolution: str = "720p",
    ) -> Path:
        """图生视频-首尾帧：指定开头和结尾画面。"""
        ...

    @abstractmethod
    async def generate_clip_text_only(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        duration_sec: float = 5.0,
        shot_index: int = 0,
        on_progress: Optional[Callable] = None,
        generate_audio: bool = False,
        resolution: str = "720p",
    ) -> Path:
        """文生视频：无参考图，仅靠 prompt 描述。"""
        ...
