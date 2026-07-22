"""统一配置 — pydantic-settings 管理 .env"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 应用基础
    APP_NAME: str = "Precision-Commerce-AI"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # 火山方舟 — 多模态分析
    API_KEY: str = ""
    BASE_URL: str = ""
    MULTIMODAL_MODEL: str = ""

    # DeepSeek — 纯文本策略
    TEXT_MODEL: str = "deepseek-v4-pro"
    TEXT_BASE_URL: str = "https://api.deepseek.com/v1/chat/completions"
    TEXT_API_KEY: str = ""

    # Seedream 生图
    SEEDREAM_IMAGE_URL: str = ""
    SEEDREAM_IMAGE_MODEL: str = ""
    IMAGE_OUTPUT_DIR: str = "output/images"
    IMAGE_MAX_CONCURRENT: int = 3

    # Seedance 图生视频
    SEEDANCE_VIDEO_URL: str = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
    SEEDANCE_VIDEO_MODEL: str = "doubao-seedance-1-5-pro-251215"
    SEEDANCE_POLL_INTERVAL: float = 5.0
    SEEDANCE_POLL_MAX: int = 60

    # 基础设施
    EDGE_PATH: str = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_URL: str = "mysql+aiomysql://root:root@localhost:3306/ecommerce_unified"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
