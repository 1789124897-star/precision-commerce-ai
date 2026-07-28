"""Task 数据访问 — API 用异步，Celery Worker 用同步。"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models import Task


class TaskRepo:
    """Celery Worker 侧同步访问。"""

    @staticmethod
    def get_by_id(db: Session, task_id: str) -> Optional[Task]:
        """按 task_id 查一条任务。"""
        return db.execute(select(Task).filter_by(task_id=task_id)).scalar_one_or_none()

    @staticmethod
    def find_stale(db: Session, cutoff: datetime) -> list[Task]:
        """找出超过 cutoff 时间仍为 RUNNING 的僵尸任务。"""
        return list(db.execute(select(Task).where(Task.status == "RUNNING", Task.updated_at < cutoff)).scalars().all())

    @staticmethod
    def set_running(db: Session, task_id: str, celery_id: str) -> Optional[Task]:
        """标记任务为 RUNNING，记下 Celery 任务 ID。"""
        task = TaskRepo.get_by_id(db, task_id)
        if not task:
            return None
        task.status = "RUNNING"
        task.celery_id = celery_id
        return task

    @staticmethod
    def set_success(db: Session, task_id: str, result_json: Any) -> Optional[Task]:
        """标记任务为 SUCCESS，写入结果。"""
        task = TaskRepo.get_by_id(db, task_id)
        if not task:
            return None
        task.status = "SUCCESS"
        task.result_json = result_json
        return task

    @staticmethod
    def set_failure(db: Session, task_id: str, error_message: str) -> Optional[Task]:
        """标记任务为 FAILURE，记录错误信息。"""
        task = TaskRepo.get_by_id(db, task_id)
        if not task:
            return None
        task.status = "FAILURE"
        task.error_message = error_message
        return task

    @staticmethod
    def set_result(db: Session, task_id: str, result_json: Any) -> Optional[Task]:
        """仅更新 result_json，不改状态（用于进度回写）。"""
        task = TaskRepo.get_by_id(db, task_id)
        if not task:
            return None
        task.result_json = result_json
        return task

    @staticmethod
    def mark_stale_failed(db: Session, tasks: list[Task], error_message: str) -> int:
        """批量将僵尸任务标为 FAILURE。"""
        for task in tasks:
            task.status = "FAILURE"
            task.error_message = error_message
        return len(tasks)


class AsyncTaskRepo:
    """FastAPI 侧异步访问。"""

    @staticmethod
    async def get_by_id(db: AsyncSession, task_id: str) -> Optional[Task]:
        """按 task_id 查一条任务 """
        result = await db.execute(select(Task).filter_by(task_id=task_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_pending(
        db: AsyncSession,
        *,
        task_id: str,
        task_type: str,
        request_json: dict,
        parent_task_id: Optional[str] = None,
    ) -> Task:
        """创建一条 PENDING 状态的任务记录。"""
        task = Task(
            task_id=task_id,
            parent_task_id=parent_task_id,
            type=task_type,
            status="PENDING",
            request_json=request_json,
        )
        db.add(task)
        await db.commit()
        return task
