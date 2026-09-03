"""统一配置 — pydantic-settings 管理 .env"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    
    # 应用基础
    APP_NAME: str = "Precision-Commerce-AI"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # 火山方舟 — 多模态分析
    VOLCANO_API_KEY: str = ""
    DOUBAO_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    DOUBAO_MODEL: str = ""

    # Kimi K3 — 多模态
    KIMI_API_KEY: str = ""
    KIMI_BASE_URL: str = "https://api.moonshot.cn/v1/chat/completions"
    KIMI_MODEL: str = "kimi-k3"

    # GPT — 多模态
    GPT_API_KEY: str = ""
    GPT_BASE_URL: str = "https://api.sudocode.chat/v1/chat/completions"
    GPT_MODEL: str = "gpt-5.6-sol"
    GPT_PROXY: str = ""  

    # DeepSeek — 纯文本策略
    DEEPSEEK_MODEL: str = "deepseek-v4-pro"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_API_KEY: str = ""

    # Seedream 生图
    SEEDREAM_IMAGE_URL: str = ""
    SEEDREAM_IMAGE_MODEL: str = ""
    IMAGE_MAX_CONCURRENT: int = 3

    # GPT 生图
    GPT_IMAGE_URL: str = "https://api.sudocode.chat/v1/images/generations"

    # Seedance 图生视频
    SEEDANCE_VIDEO_URL: str = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
    SEEDANCE_VIDEO_MODEL: str = "doubao-seedance-1-5-pro-251215"
    SEEDANCE_POLL_INTERVAL: float = 5.0
    SEEDANCE_POLL_MAX: int = 60

    # 图床（cloudflared 隧道）
    CLOUDFLARED_BIN: str = ""

    # APIMart 中转 — Seedance 2.0 Mini 视频
    APIMART_API_KEY: str = ""
    APIMART_VIDEO_MODEL: str = "seedance-2.0-mini"
    APIMART_VIDEO_URL: str = "https://api.apimart.ai/v1/videos/generations"
    APIMART_VIDEO_TASK_URL: str = "https://api.apimart.ai/v1/tasks" 
    APIMART_PROXY: str = ""  # 走代理时填 http://127.0.0.1:7890

    # 基础设施
    EDGE_PATH: str = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_URL: str = "mysql+aiomysql://root:root@localhost:3306/ecommerce_unified"

    # 1688 反爬
    ALIBABA_1688_EMAIL: str = ""
    ALIBABA_1688_PASSWORD: str = ""

    # 代理
    PROXY_PROVIDER: str = ""
    PROXY_HOST: str = ""
    PROXY_PORT: str = ""
    PROXY_USERNAME: str = ""
    PROXY_PASSWORD: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
