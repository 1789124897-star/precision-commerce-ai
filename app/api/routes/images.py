"""生图路由"""
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import save_upload
from app.models import Task
from app.tasks.image_gen import image_gen_task

router = APIRouter(prefix="/images", tags=["Images"])


@router.post("/generate")
async def submit_image(
    images_data: str = Form(...),
    ref_images: list[UploadFile] = File(default_factory=list),
    size: str = Form("2048x2048"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ref_image_paths = [save_upload(f, "image_gen") for f in ref_images if f]

    task_id = uuid.uuid4().hex[:8]
    task = Task(
        task_id=task_id,
        type="image_gen",
        status="PENDING",
        request_json={
            "images_data": images_data,
            "ref_image_paths": ref_image_paths,
            "size": size,
            "task_id": task_id,
        },
    )
    db.add(task)
    await db.commit()

    image_gen_task.delay(task_id=task_id)

    return {"data": {"task_id": task_id, "task_type": "image_generation"}, "message": "ok"}
