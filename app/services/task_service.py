"""Task 创建与下发。"""
import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task
from app.models.task import gen_task_id
from app.repositories.task_repo import AsyncTaskRepo


def _make_request_hash(request_json: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(request_json, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


class TaskService:
    """Task 创建与下发"""

    @staticmethod
    async def create_and_dispatch(
        db: AsyncSession,
        *,
        task_type: str,
        request_json: dict[str, Any],
        celery_task: Any,
        parent_task_id: str | None = None,
    ) -> Task:

        request_hash = _make_request_hash(request_json)
        existing = await AsyncTaskRepo.find_duplicate(db, task_type, request_hash)
        if existing:
            return existing

        task = await AsyncTaskRepo.create_pending(
            db,
            task_id=gen_task_id(),
            task_type=task_type,
            request_json=request_json,
            request_hash=request_hash,
            parent_task_id=parent_task_id,
        )
        celery_task.delay(task_id=task.task_id)
        return task
