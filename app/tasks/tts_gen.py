"""TTS 配音 Celery 任务 — 从 video.py 同步调用收敛为异步管道"""
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
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def tts_gen_task(self, task_id: str):
    logger.info("开始 task_id=%s", task_id)
    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "RUNNING"
            task.celery_id = self.request.id
            db.commit()

    try:
        result = TTSEngine().run_sync(**task.request_json)
    except Exception as e:
        logger.exception("失败 task_id=%s", task_id)
        with SyncSession() as db:
            task = TaskRepo.get_by_id(db, task_id)
            if task:
                task.status = "FAILURE"
                task.error_message = str(e)
                db.commit()
        raise

    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "SUCCESS"
            task.result_json = result
            db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"task_id": task_id, "status": "SUCCESS"}
