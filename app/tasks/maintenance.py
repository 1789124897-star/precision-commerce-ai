import logging
from datetime import datetime, timedelta, timezone

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.repositories.task_repo import TaskRepo

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="cleanup_stale_tasks",
    priority=1,
    soft_time_limit=120,
    time_limit=180,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=2,
    retry_jitter=True,
)
def cleanup_stale_tasks(self):
    with SyncSession() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        stale = TaskRepo.find_stale(db, cutoff)
        # 重新绑定到当前 session 再改状态（find 已在同 session）
        count = TaskRepo.mark_stale_failed(
            db, stale, "任务执行超时（>2h），已自动终止"
        )
        db.commit()

    if count:
        logger.warning("清理 %d 个僵尸任务", count)
    return {"cleaned": count}
