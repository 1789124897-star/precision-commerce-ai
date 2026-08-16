""" 任务轮询路由 """
import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.task import TASK_STATUSES, TASK_TYPES, Task
from app.repositories.task_repo import AsyncTaskRepo

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("")
async def list_tasks(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    task_type: str = Query("", alias="type", description="任务类型筛选"),
    status: str = Query("", description="状态筛选"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """任务历史：分页 + 筛选 + 总数"""
    if task_type and task_type not in TASK_TYPES:
        return {"data": None, "message": f"无效的任务类型: {task_type}，合法值: {TASK_TYPES}"}
    if status and status not in TASK_STATUSES:
        return {"data": None, "message": f"无效的状态: {status}，合法值: {TASK_STATUSES}"}

    base = select(Task)
    count_base = select(func.count(Task.id))
    if task_type:
        base = base.where(Task.type == task_type)
        count_base = count_base.where(Task.type == task_type)
    if status:
        base = base.where(Task.status == status)
        count_base = count_base.where(Task.status == status)

    result = await db.execute(
        base.order_by(desc(Task.id)).limit(limit).offset(offset)
    )
    tasks = result.scalars().all()
    total_result = await db.execute(count_base)
    total = total_result.scalar() or 0

    return {
        "data": {
            "tasks": [{
                "id": t.id,
                "task_id": t.task_id,
                "type": t.type,
                "status": t.status,
                "result_json": t.result_json,
                "error_message": t.error_message,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            } for t in tasks],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
        "message": "ok",
    }


@router.get("/export")
async def export_tasks(
    task_type: str = Query("", alias="type", description="任务类型筛选"),
    status: str = Query("", description="状态筛选"),
    db: AsyncSession = Depends(get_db),
):
    """导出任务历史为 CSV"""
    if task_type and task_type not in TASK_TYPES:
        return {"data": None, "message": f"无效的任务类型: {task_type}，合法值: {TASK_TYPES}"}
    if status and status not in TASK_STATUSES:
        return {"data": None, "message": f"无效的状态: {status}，合法值: {TASK_STATUSES}"}

    base = select(Task).order_by(desc(Task.id))
    if task_type:
        base = base.where(Task.type == task_type)
    if status:
        base = base.where(Task.status == status)

    result = await db.execute(base)
    tasks = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["时间", "任务ID", "类型", "状态", "错误信息", "结果摘要"])
    for t in tasks:
        summary = ""
        if t.result_json:
            summary = str(t.result_json)[:200]
        writer.writerow([
            t.created_at.isoformat() if t.created_at else "",
            t.task_id or "",
            t.type or "",
            t.status or "",
            t.error_message or "",
            summary,
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=tasks_export.csv"},
    )


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
