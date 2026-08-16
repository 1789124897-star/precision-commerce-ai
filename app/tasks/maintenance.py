import logging
from datetime import datetime, timedelta, timezone

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.repositories.task_repo import TaskRepo

logger = logging.getLogger(__name__)


@celery_app.task(
    name="cleanup_stale_tasks",
    priority=1,
    soft_time_limit=120,
    time_limit=180,
)
def cleanup_stale_tasks():
    """每 30 分钟将卡在 RUNNING 超 2 小时的任务标为失败。"""
    with SyncSession() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        stale = TaskRepo.find_stale(db, cutoff)
        count = TaskRepo.mark_stale_failed(db, stale, "任务执行超时（>2h），已自动终止")
        db.commit()

    if count:
        logger.warning("清理 %d 个僵尸任务", count)
    return {"cleaned": count}
