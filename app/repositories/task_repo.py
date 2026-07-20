from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models import Task


class TaskRepo:
    
    @staticmethod
    def get_by_id(db: Session, task_id: str):
        return db.query(Task).filter_by(task_id=task_id).first()

    @staticmethod
    def find_stale(db: Session, cutoff: datetime):
        return db.query(Task).filter(Task.status == "RUNNING", Task.updated_at < cutoff).all()


class AsyncTaskRepo:

    @staticmethod
    async def get_by_id(db: AsyncSession, task_id: str):
        result = await db.execute(select(Task).filter_by(task_id=task_id))
        return result.scalar_one_or_none()
