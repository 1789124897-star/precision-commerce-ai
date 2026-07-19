"""FastAPI 应用入口"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import async_engine, Base
from app.core.exceptions import AppException
from app.core.logging import setup_logging
from app.core.paths import OUTPUT_DIR, IMAGE_DIR, AUDIO_DIR, VIDEO_DIR
import app.models  # noqa: F401 — 注册 ORM 模型

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title=settings.APP_NAME, docs_url="/docs", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,    
        content={"code": -1, "message": exc.message, "data": None},
    )


# ── 路由注册 ──
# 业务顺序：采集 → 分析 → 生图 → 视频
from app.api.routes import health, scraper, analysis, tasks, images, video

app.include_router(health.router, prefix=settings.API_PREFIX)
app.include_router(scraper.router, prefix=settings.API_PREFIX)
app.include_router(analysis.router, prefix=settings.API_PREFIX)
app.include_router(tasks.router, prefix=settings.API_PREFIX)
app.include_router(images.router, prefix=settings.API_PREFIX)
app.include_router(video.router, prefix=settings.API_PREFIX)

# ── 静态文件 & 产物目录 ──
for d in (IMAGE_DIR, AUDIO_DIR, VIDEO_DIR):
    d.mkdir(parents=True, exist_ok=True)

app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
app.mount("/static", StaticFiles(directory="static"), name="static")
