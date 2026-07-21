"""营销策略生成 Celery 任务"""
import logging

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.models import Strategy
from app.repositories.task_repo import TaskRepo
from app.services.analysis import AnalysisService

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="generate_strategies",
    priority=7,
    soft_time_limit=300,
    time_limit=420,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def strategy_task(self, task_id: str):
    logger.info("开始 task_id=%s", task_id)
    with SyncSession() as db:
        task = TaskRepo.set_running(db, task_id, self.request.id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        request_json = dict(task.request_json or {})
        parent_task_id = task.parent_task_id or ""
        db.commit()

    try:
        result = AnalysisService().run_strategies_sync(**request_json)
    except Exception as e:
        logger.exception("失败 task_id=%s", task_id)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, str(e))
            db.commit()
        raise

    with SyncSession() as db:
        task = TaskRepo.set_success(db, task_id, result)
        if task:
            for stype, text in result.get("strategies", {}).items():
                db.add(
                    Strategy(
                        task_id=task_id,
                        analysis_task_id=parent_task_id,
                        strategy_type=stype,
                        result_text=text,
                    )
                )
        db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"task_id": task_id, "status": "SUCCESS"}
