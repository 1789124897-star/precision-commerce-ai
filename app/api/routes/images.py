"""生图路由"""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import save_upload
from app.models.task import TASK_TYPE_IMAGE_GEN
from app.schemas.images import ImageGenRequest
from app.services.task_service import TaskService
from app.tasks.image_gen import generate_images_task

router = APIRouter(prefix="/images", tags=["Images"])


@router.post("/upload-images")
async def upload_images(files: list[UploadFile] = File(...)) -> dict:
    return {"data": {"images": [save_upload(f, "image_gen") for f in files]}, "message": "ok"}


@router.post("/generate")
async def submit_image(
    body: ImageGenRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    task = await TaskService.create_and_dispatch(
        db,
        task_type=TASK_TYPE_IMAGE_GEN,
        request_json={
            "prompts": [s.model_dump() for s in body.prompts],
            "size": body.size,
            "model": body.model,
            "ref_image_paths": body.ref_image_paths,
        },
        celery_task=generate_images_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "image_generation"}, "message": "ok"}
