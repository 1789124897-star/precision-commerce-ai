"""产品分析路由"""
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import save_upload
from app.models import Task
from app.schemas.analysis import AnalysisSubmitRequest, StrategyRequest
from app.tasks.analysis import analyze_product_task
from app.tasks.strategy import strategy_task

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.post("/submit")
async def submit_analysis(
    name: str = Form(...),
    function: str = Form(...),
    price: str = Form(...),
    extra: str = Form(""),
    images: list[UploadFile] = File(default_factory=list),
    custom_prompt: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    body = AnalysisSubmitRequest(
        name=name,
        function=function,
        price=price,
        extra=extra,
        custom_prompt=custom_prompt,
    )

    image_paths = [save_upload(f, "analysis") for f in images if f]

    task_id = uuid.uuid4().hex[:8]
    
    task = Task(
        task_id=task_id,
        type="analysis",
        status="PENDING",
        request_json={**body.model_dump(), "image_paths": image_paths},
    )
    db.add(task)
    await db.commit()

    analyze_product_task.delay(task_id=task_id)

    return {"data": {"task_id": task_id, "task_type": "analysis"}, "message": "ok"}


@router.post("/strategies")
async def do_submit_strategies(body: StrategyRequest, db: AsyncSession = Depends(get_db)) -> dict:

    task_id = uuid.uuid4().hex[:8]
    
    task = Task(
        task_id=task_id,
        parent_task_id=body.parent_task_id,
        type="strategy",
        status="PENDING",
        request_json={"analysis": body.analysis, "system_prompt": body.system_prompt},
    )
    db.add(task)
    await db.commit()

    strategy_task.delay(task_id=task_id)

    return {"data": {"task_id": task_id, "task_type": "strategy"}, "message": "ok"}
