"""AI 生图 Celery 任务"""
import logging

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.core.exceptions import AppException
from app.models.task import STATUS_SUCCESS
from app.repositories.task_repo import TaskRepo
from app.services.image_gen_service import ImageGenService

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="generate_images",
    soft_time_limit=300,
    time_limit=420,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def generate_images_task(self, task_id: str):

    logger.info("开始 task_id=%s", task_id)

    with SyncSession() as db:
        task = TaskRepo.set_running(db, task_id, self.request.id)
        if not task:
            logger.error("任务不存在 task_id=%s", task_id)
            return {"task_id": task_id, "status": "NOT_FOUND"}
        request_json = task.request_json or {}
        db.commit()

    try:
        result = ImageGenService().run_sync(**request_json, task_id=task_id)
    except AppException as e:
        logger.error("业务失败 task_id=%s: %s", task_id, e.message)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, e.message)
            db.commit()
        return {"task_id": task_id, "status": "FAILURE"}
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
    return {"task_id": task_id, "status": STATUS_SUCCESS}
