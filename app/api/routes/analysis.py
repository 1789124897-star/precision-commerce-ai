""" 产品分析路由 """
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import save_upload
from app.models.task import TASK_TYPE_ANALYSIS, TASK_TYPE_STRATEGY
from app.schemas.analysis import AnalysisSubmitRequest, StrategyRequest
from app.services.task_service import TaskService
from app.tasks.analysis import analyze_product_task
from app.tasks.strategy import generate_strategies_task

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.post("/submit")
async def submit_analysis(
    name: str = Form(...),
    function: str = Form(...),
    price: str = Form(...),
    extra: str = Form(""),
    images: list[UploadFile] = File(default_factory=list),
    custom_prompt: str = Form(""),
    model: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    body = AnalysisSubmitRequest(
        name=name,
        function=function,
        price=price,
        extra=extra,
        custom_prompt=custom_prompt,
        model=model,
    )
    image_paths = [save_upload(f, "analysis") for f in images if f]

    task = await TaskService.create_and_dispatch(
        db,
        task_type=TASK_TYPE_ANALYSIS,
        request_json={
            "name": body.name,
            "function": body.function,
            "price": body.price,
            "extra": body.extra,
            "custom_prompt": body.custom_prompt,
            "model": body.model,
            "image_paths": image_paths,
        },
        celery_task=analyze_product_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "analysis"}, "message": "ok"}


@router.post("/strategies")
async def do_submit_strategies(
    body: StrategyRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    task = await TaskService.create_and_dispatch(
        db,
        task_type=TASK_TYPE_STRATEGY,
        request_json={
            "analysis": body.analysis, 
            "system_prompt": body.system_prompt, 
            "model": body.model,
        },
        celery_task=generate_strategies_task,
        parent_task_id=body.parent_task_id,
    )
    return {"data": {"task_id": task.task_id, "task_type": "strategy"}, "message": "ok"}
