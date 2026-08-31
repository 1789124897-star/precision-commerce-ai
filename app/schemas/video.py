""" Video Pydantic 模型 """

from typing import Optional

from pydantic import BaseModel, Field


class GenerateScriptRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    segments: int = Field(default=8, ge=5, le=12)
    system_prompt: str = Field(default="", max_length=3000)


class GenerateTTSRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice: str = ""
    rate: str = ""
    parent_task_id: Optional[str] = None  



class ComposeVideoRequest(BaseModel):
    images: list[str]
    audio_path: str
    srt_path: str
    aspect_ratio: str = "9:16"
    resolution: str = "720p"
    transition: str = "fade"
    quality_check: bool = True
    parent_task_id: Optional[str] = None  


class ShotSchema(BaseModel):
    image_index: int = 0
    image_url: str = ""
    first_frame_url: str = ""
    last_frame_url: str = ""
    scene_prompt: str = ""
    scene_prompt_en: str = ""  # 英文版 → Seedance API
    duration_sec: float = 5.0
    overlay_text: str = ""
    resolution: str = "720p"
    clip_path: str = ""  # 前端预生成的 clip_url 映射


class ComposePremiumRequest(BaseModel):
    shots: list[ShotSchema]
    images: list[str]
    audio_path: str
    srt_path: str = ""
    aspect_ratio: str = "9:16"
    generate_audio: bool = False
    resolution: str = "720p"
    seedance_model: str = ""  # 视频模型：Mini 走 APIMart，其余走火山
    segment_durations: Optional[list[float]] = None
    parent_task_id: Optional[str] = None  # 上游 TTS 任务


class GenerateShotRequest(BaseModel):
    """独立生成单个分镜"""
    image_url: str = ""
    first_frame_url: str = ""
    last_frame_url: str = ""
    scene_prompt: str = ""
    voiceover: str = ""  # 台词：有声模式下拼进 prompt 让模型念出
    duration_sec: float = 4.0
    aspect_ratio: str = "9:16"
    generate_audio: bool = False
    resolution: str = "720p"
    shot_index: int = 0
    seedance_model: str = ""  
    parent_task_id: Optional[str] = None  # 上游 TTS 任务
