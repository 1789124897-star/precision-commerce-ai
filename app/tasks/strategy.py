from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.models import Strategy
from app.repositories.task_repo import TaskRepo
from app.services.analysis import AnalysisService


@celery_app.task(
    bind=True,
    name="generate_strategies",
    priority=7,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
    soft_time_limit=300,
    time_limit=420,
)
def strategy_task(self, task_id: str):
    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "RUNNING"
            task.celery_id = self.request.id
            db.commit()

    try:
        result = AnalysisService().run_strategies_sync(**task.request_json)
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
        analysis_task_id = task.parent_task_id if task else ""
        for stype, text in result.get("strategies", {}).items():
            db.add(Strategy(
                task_id=task_id,
                analysis_task_id=analysis_task_id,
                strategy_type=stype,
                result_text=text,
            ))
        db.commit()

    return {"task_id": task_id, "status": "SUCCESS"}
