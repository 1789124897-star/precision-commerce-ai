from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.models import Product
from app.repositories.task_repo import TaskRepo
from app.services.scraper import ImageScraper


@celery_app.task(
    bind=True,
    name="scrape_product",
    priority=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def scrape_product_task(self, url: str, task_id: str):
    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "RUNNING"
            task.celery_id = self.request.id
            db.commit()

    try:
        result = ImageScraper().scrape(url, task_id)
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
        product = Product(
            task_id=task_id,
            url=url,
            name=result.get("name", ""),
            folder=result.get("folder", ""),
            image_count=result.get("image_count", 0),
        )
        db.add(product)
        db.commit()

    return {"task_id": task_id, "status": "SUCCESS"}
