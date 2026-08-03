"""FastAPI 应用入口"""
import logging
from contextlib import asynccontextmanager

from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import app.models as _models  # noqa: F401 注册 ORM 模型
from alembic import command
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import setup_logging
from app.core.paths import OUTPUT_DIR

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.file_config.read("alembic.ini", encoding="utf-8")
    command.upgrade(alembic_cfg, "head")

    # 启动时清理上次遗留的 RUNNING 状态（Worker 重启导致）
    from app.core.database import SyncSession
    from app.models.task import STATUS_FAILURE, Task
    from sqlalchemy import update
    with SyncSession() as db:
        db.execute(
            update(Task).where(Task.status == "RUNNING").values(
                status=STATUS_FAILURE,
                error_message="服务重启，任务被中断",
            )
        )
        db.commit()

    yield


app = FastAPI(title=settings.APP_NAME, docs_url="/docs", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 全局异常处理 ──
@app.exception_handler(AppException)
async def handle_app_exception(_req: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"data": None, "message": exc.message},
    )


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"data": None, "message": "服务器内部错误"},
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
