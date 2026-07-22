"""1688 采集 Celery 任务"""
import logging

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.models import Product
from app.repositories.task_repo import TaskRepo
from app.services.scraper import ImageScraper

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="scrape_product",
    priority=5,
    soft_time_limit=300,
    time_limit=420,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def scrape_product_task(self, task_id: str):
    logger.info("开始 task_id=%s", task_id)
    with SyncSession() as db:
        task = TaskRepo.set_running(db, task_id, self.request.id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        request_json = dict(task.request_json or {})
        db.commit()

    url = request_json.get("url", "")
    # 去掉 1688 追踪参数，避免 URL 过长超出数据库字段
    if "?" in url:
        url = url.split("?")[0]
    try:
        result = ImageScraper().scrape(url, task_id)
    except Exception as e:
        logger.exception("失败 task_id=%s", task_id)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, str(e))
            db.commit()
        raise

    with SyncSession() as db:
        task = TaskRepo.set_success(db, task_id, result)
        if task:
            db.add(
                Product(
                    task_id=task_id,
                    url=url,
                    name=result.get("name", ""),
                    folder=result.get("folder", ""),
                    image_count=result.get("image_count", 0),
                )
            )
        db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"folder": result.get("folder"), "image_count": result.get("image_count")}
