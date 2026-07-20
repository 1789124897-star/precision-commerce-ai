import logging
from datetime import UTC, datetime, timedelta

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.repositories.task_repo import TaskRepo

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="cleanup_stale_tasks",
    priority=1,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=2,
    retry_jitter=True,
)
def cleanup_stale_tasks(self):
    with SyncSession() as db:
        cutoff = datetime.now(UTC) - timedelta(hours=2)
        stale = TaskRepo.find_stale(db, cutoff)

    try:
        with SyncSession() as db:
            for task in stale:
                task.status = "FAILURE"
                task.error_message = "任务执行超时（>2h），已自动终止"
            db.commit()
    except Exception:
        logger.exception("清理僵尸任务失败")
        raise

    if stale:
        logger.warning("清理 %d 个僵尸任务", len(stale))
    return {"cleaned": len(stale)}
