"""生图路由"""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import save_upload
from app.models.task import TASK_TYPE_IMAGE_GEN
from app.services.task_service import TaskService
from app.tasks.image_gen import generate_images_task

router = APIRouter(prefix="/images", tags=["Images"])


@router.post("/generate")
async def submit_image(
    prompts: str = Form(...),
    ref_images: list[UploadFile] = File(default_factory=list),
    size: str = Form("2048x2048"),
    model: str = Form(""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ref_image_paths = [save_upload(f, "image_gen") for f in ref_images if f]

    task = await TaskService.create_and_dispatch(
        db,
        task_type=TASK_TYPE_IMAGE_GEN,
        request_json={
            "prompts": prompts,
            "ref_image_paths": ref_image_paths,
            "size": size,
            "model": model,
        },
        celery_task=generate_images_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "image_generation"}, "message": "ok"}
