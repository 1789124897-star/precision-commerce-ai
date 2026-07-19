"""商品分析 Celery 任务"""
import logging

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.models import Analysis
from app.repositories.task_repo import TaskRepo
from app.services.analysis import AnalysisService

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="analyze_product",
    priority=7,
    soft_time_limit=300,
    time_limit=420,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def analyze_product_task(self, task_id: str):
    logger.info("开始 task_id=%s", task_id)
    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "RUNNING"
            task.celery_id = self.request.id
            db.commit()

    try:
        result = AnalysisService().run_sync(**task.request_json)
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
        kwargs = task.request_json or {}
        analysis = Analysis(
            task_id=task_id,
            product_name=kwargs.get("name", result.get("product_name", "")),
            product_function=kwargs.get("function", ""),
            price_range=kwargs.get("price", ""),
            extra_info=kwargs.get("extra", ""),
            image_paths=str(kwargs.get("image_paths", [])),
            result_text=result.get("analysis", ""),
        )
        db.add(analysis)
        db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"task_id": task_id, "status": "SUCCESS"}
