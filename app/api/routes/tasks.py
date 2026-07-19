"""任务轮询路由"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.database import get_db, SyncSession
from app.models.task import Task
from app.repositories.task_repo import AsyncTaskRepo, TaskRepo

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("")
async def list_tasks(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """任务列表，按更新时间倒序"""
    result = await db.execute(
        select(Task).order_by(desc(Task.id)).limit(limit)
    )
    tasks = result.scalars().all()
    return {
        "data": [{
            "id": t.id,
            "task_id": t.task_id,
            "type": t.type,
            "status": t.status,
            "result_json": t.result_json,
            "error_message": t.error_message,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        } for t in tasks],
        "message": "ok",
    }


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    """取消任务：标记 FAILURE + 撤回 Celery 任务"""
    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if not task:
            return {"data": None, "message": "任务不存在"}
        if task.status in ("SUCCESS", "FAILURE"):
            return {"data": None, "message": f"任务已结束 ({task.status})"}

        # 撤回 Celery 任务（如果正在执行）
        if task.celery_id:
            celery_app.control.revoke(task.celery_id, terminate=True)

        task.status = "FAILURE"
        task.error_message = "用户手动取消"
        db.commit()

    return {"data": {"task_id": task_id, "status": "FAILURE"}, "message": "已取消"}


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
