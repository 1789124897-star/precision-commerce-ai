from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.models import Analysis
from app.repositories.task_repo import TaskRepo
from app.services.analysis import run_analysis_sync


@celery_app.task(
    bind=True,
    name="analyze_product",
    priority=7,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def analyze_product_task(self, task_id: str):
    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "RUNNING"
            task.celery_id = self.request.id
            db.commit()

    try:
        result = run_analysis_sync(**task.request_json)
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

    return {"task_id": task_id, "status": "SUCCESS"}
