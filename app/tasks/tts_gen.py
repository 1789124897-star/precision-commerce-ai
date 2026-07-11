"""TTS 配音 Celery 任务 — 从 video.py 同步调用收敛为异步管道"""
import asyncio

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.repositories.task_repo import TaskRepo
from app.services.tts_service import TTSEngine


def _sync_synthesize(**kwargs) -> dict:
    return asyncio.run(TTSEngine.synthesize_from_script(**kwargs))


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
    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "RUNNING"
            task.celery_id = self.request.id
            db.commit()

    try:
        result = _sync_synthesize(**task.request_json)
    except Exception as e:
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

    return {"task_id": task_id, "status": "SUCCESS"}
