"""TTS 配音 Celery 任务"""
import logging

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.repositories.task_repo import TaskRepo
from app.services.tts_service import TTSEngine

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="generate_tts",
    priority=9,
    soft_time_limit=300,
    time_limit=420,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def generate_tts_task(self, task_id: str):
    logger.info("开始 task_id=%s", task_id)
    with SyncSession() as db:
        task = TaskRepo.set_running(db, task_id, self.request.id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        request_json = dict(task.request_json or {})
        db.commit()

    try:
        result = TTSEngine().run_sync(**request_json, task_id=task_id)
    except Exception as e:
        logger.exception("失败 task_id=%s", task_id)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, str(e))
            db.commit()
        raise

    with SyncSession() as db:
        TaskRepo.set_success(db, task_id, result)
        db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"task_id": task_id, "status": "SUCCESS"}
