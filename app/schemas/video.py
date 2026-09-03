""" Video Pydantic 模型 """

from typing import Literal, Optional

from pydantic import BaseModel, Field

VideoResolution = Literal["480p", "720p", "1080p"]


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
    resolution: VideoResolution
    transition: str = "fade"
    quality_check: bool = True
    parent_task_id: Optional[str] = None  


class ShotSchema(BaseModel):
    duration_sec: float = 5.0
    clip_path: str = "" 


class ComposePremiumRequest(BaseModel):
    shots: list[ShotSchema]
    audio_path: str = ""
    srt_path: str = ""
    parent_task_id: Optional[str] = None 


class GenerateShotRequest(BaseModel):
    """独立生成单个分镜"""
    first_frame_url: str = ""
    last_frame_url: str = ""
    scene_prompt: str = ""
    voiceover: str = ""  # 台词
    duration_sec: float = 4.0
    aspect_ratio: str = "9:16"
    generate_audio: bool = False  # 是否有声
    resolution: VideoResolution
    shot_index: int = 0
    video_model: str = ""   
    parent_task_id: Optional[str] = None 
