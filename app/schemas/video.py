"""Video Pydantic 模型 —— 兼容前后端字段名"""


from pydantic import BaseModel, Field


class GenerateScriptRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    segments: int = Field(default=8, ge=5, le=12)
    system_prompt: str = Field(default="", max_length=3000)
    tts_rate: str = Field(default="+0%", max_length=10)


class GenerateTTSRequest(BaseModel):
    script_path: str = ""
    text: str = ""
    task_id: str = ""
    voice: str = ""
    rate: str = ""



class ComposeVideoRequest(BaseModel):
    images: list[str]
    audio_path: str
    srt_path: str
    task_id: str = ""
    mode: str = "fast"
    aspect_ratio: str = "9:16"
    quality_check: bool = True
    transition: str = ""
    ai_style: str = ""


class ShotSchema(BaseModel):
    image_index: int = 0
    image_url: str = ""
    first_frame_url: str = ""
    last_frame_url: str = ""
    scene_prompt: str = ""
    duration_sec: float = 5.0
    overlay_text: str = ""
    resolution: str = "720p"
    clip_path: str = ""  # 前端预生成的 clip_url 映射


class ComposePremiumRequest(BaseModel):
    shots: list[ShotSchema]
    images: list[str]
    audio_path: str
    srt_path: str = ""
    task_id: str = ""
    aspect_ratio: str = "9:16"
    generate_audio: bool = False
    resolution: str = "720p"
    segment_durations: list[float] | None = None


class GenerateShotRequest(BaseModel):
    """独立生成单个分镜"""
    image_url: str = ""
    first_frame_url: str = ""
    last_frame_url: str = ""
    scene_prompt: str = ""
    duration_sec: float = 5.0
    aspect_ratio: str = "9:16"
    generate_audio: bool = False
    resolution: str = "720p"
    shot_index: int = 0
