"""爬虫模块请求/响应模型"""
from pydantic import BaseModel, Field, field_validator


class ScrapeRequest(BaseModel):
    url: str = Field(
        ...,
        description="1688 商品链接",
        examples=["https://detail.1688.com/offer/864325626215.html"],
    )

    @field_validator("url")
    @classmethod
    def must_be_1688(cls, v: str) -> str:
        v = v.strip()
        if "?" in v:
            v = v.split("?")[0]
        if not v:
            raise ValueError("请输入商品链接")
        if "1688.com" not in v and "alibaba.com" not in v:
            raise ValueError("仅支持 1688 / alibaba 商品链接")
        return v
