"""Task 创建与下发。"""
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task
from app.models.task import gen_task_id
from app.repositories.task_repo import AsyncTaskRepo


class TaskService:

    @staticmethod
    async def create_and_dispatch(
        db: AsyncSession,
        *,
        task_type: str,
        request_json: dict[str, Any],
        celery_task: Any,
        parent_task_id: Optional[str] = None,
    ) -> Task:
        task = await AsyncTaskRepo.create_pending(
            db,
            task_id=gen_task_id(),
            task_type=task_type,
            request_json=request_json,
            parent_task_id=parent_task_id,
        )
        celery_task.delay(task_id=task.task_id)
        return task
