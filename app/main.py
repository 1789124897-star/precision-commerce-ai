"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import app.models as _models  # noqa: F401 注册 ORM 模型
from alembic import command
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.paths import OUTPUT_DIR

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.file_config.read("alembic.ini", encoding="utf-8")
    command.upgrade(alembic_cfg, "head")
    yield


app = FastAPI(title=settings.APP_NAME, docs_url="/docs", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 路由注册 ──
# 业务顺序：采集 → 分析 → 生图 → 视频
from app.api.routes import analysis, health, images, scraper, tasks, video  # noqa: E402 — 路由注册需放在 app 创建之后

app.include_router(health.router, prefix=settings.API_PREFIX)
app.include_router(scraper.router, prefix=settings.API_PREFIX)
app.include_router(analysis.router, prefix=settings.API_PREFIX)
app.include_router(tasks.router, prefix=settings.API_PREFIX)
app.include_router(images.router, prefix=settings.API_PREFIX)
app.include_router(video.router, prefix=settings.API_PREFIX)

# ── 静态文件 ──
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
app.mount("/static", StaticFiles(directory="static"), name="static")
