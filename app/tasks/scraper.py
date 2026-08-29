"""1688 采集 Celery 任务"""
import logging

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.core.exceptions import AppException
from app.models import Product
from app.repositories.task_repo import TaskRepo
from app.services.scraper import ImageScraper

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="scrape_product",
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
            logger.error("任务不存在 task_id=%s", task_id)
            return {"task_id": task_id, "status": "NOT_FOUND"}
        url = (task.request_json or {}).get("url", "")
        db.commit()

    try:
        result = ImageScraper().scrape(url, task_id)
    except AppException as e:
        # 业务/永久性错误：重试无意义，标记失败后直接结束
        logger.error("业务失败 task_id=%s: %s", task_id, e.message)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, e.message)
            db.commit()
        return {"task_id": task_id, "status": "FAILURE"}
    except Exception as e:
        # 临时性错误（网络/接口抖动）：标记失败 + raise 触发自动重试
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
                    image_count=result.get("image_count", 0),
                )
            )
        db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"folder": result.get("folder"), "image_count": result.get("image_count")}
