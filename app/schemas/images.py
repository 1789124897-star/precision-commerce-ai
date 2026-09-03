"""图片生成请求模型"""

from pydantic import BaseModel, Field


class ImageSpec(BaseModel):

    position: int = Field(ge=1)
    prompt: str = Field(min_length=1)
    source: str = ""
    type: str = ""


class ImageGenRequest(BaseModel):
    """生图请求（对应前端两个入口的完整参数）"""

    prompts: list[ImageSpec] = Field(min_length=1)
    size: str = Field(default="2048x2048", pattern=r"^\d+x\d+$")
    model: str = ""
    ref_image_paths: list[str] = Field(default_factory=list)
