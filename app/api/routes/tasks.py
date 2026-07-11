"""任务轮询路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.task_repo import AsyncTaskRepo

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    task = await AsyncTaskRepo.get_by_id(db, task_id)
    if not task:
        return {"data": None, "message": "任务不存在"}
    return {
        "data": {
            "task_id": task.task_id,
            "type": task.type,
            "status": task.status,
            "result": task.result_json,
            "error_message": task.error_message,
        },
        "message": "ok",
    }
