"""Celery 实例 — 含重试策略、Beat 定时任务、队列路由"""
from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()  # worker 启动时初始化日志（不依赖 FastAPI main）

celery_app = Celery(
    "precision_commerce",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.scraper",
        "app.tasks.analysis",
        "app.tasks.strategy",
        "app.tasks.image_gen",
        "app.tasks.video",
        "app.tasks.maintenance",
        "app.tasks.script_gen",
        "app.tasks.tts_gen",
    ],
)

celery_app.conf.update(
    # ── 序列化：任务参数和结果统一用 JSON ──
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ── 任务追踪 ──
    task_track_started=True,

    # ── 可靠性 ──
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # ── 时区 ──
    timezone="Asia/Shanghai",
    enable_utc=False,

    # ── 日志：不劫持 root logger，用我们自己的配置 ──
    worker_hijack_root_logger=False,

    # ── 多队列：按任务类型隔离，防止 CPU 密集任务饿死 IO 密集任务 ──
    task_queues=(
        Queue("video",   routing_key="video.#",   queue_arguments={"x-max-priority": 10}),
        Queue("ai",      routing_key="ai.#",      queue_arguments={"x-max-priority": 10}),
        Queue("compose", routing_key="compose.#", queue_arguments={"x-max-priority": 10}),
        Queue("scraper", routing_key="scraper.#", queue_arguments={"x-max-priority": 10}),
        Queue("default", routing_key="default.#", queue_arguments={"x-max-priority": 10}),
    ),
    task_routes={
        "generate_script":      {"queue": "video"},
        "generate_tts":         {"queue": "video"},
        "compose_video":        {"queue": "compose"},
        "compose_premium_video": {"queue": "compose"},
        "generate_shot":        {"queue": "compose"},
        "analyze_product":      {"queue": "ai"},
        "generate_strategies":  {"queue": "ai"},
        "generate_images":      {"queue": "ai"},
        "scrape_product":       {"queue": "scraper"},
        "cleanup_stale_tasks":  {"queue": "default"},
    },
    task_default_priority=5,

    # ── Beat 定时任务（调度器） ──
    beat_schedule={
        "cleanup-stale-tasks-every-30min": {
            "task": "cleanup_stale_tasks",
            "schedule": crontab(minute="*/30"),
        },
    },
)
