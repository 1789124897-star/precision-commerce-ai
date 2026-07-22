"""生图路由"""
import httpx
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import save_upload
from app.services.task_service import TaskService
from app.tasks.image_gen import generate_images_task

router = APIRouter(prefix="/images", tags=["Images"])


@router.get("/proxy")
async def proxy_image(url: str = Query(..., description="图片 CDN URL")):
    """代理拉取 CDN 图片，绕过浏览器 CORS 限制"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
    return Response(
        content=r.content,
        media_type=r.headers.get("content-type", "image/png"),
    )


@router.post("/generate")
async def submit_image(
    images_data: str = Form(...),
    ref_images: list[UploadFile] = File(default_factory=list),
    size: str = Form("2048x2048"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ref_image_paths = [save_upload(f, "image_gen") for f in ref_images if f]

    task = await TaskService.create_and_dispatch(
        db,
        task_type="image_gen",
        request_json={
            "images_data": images_data,
            "ref_image_paths": ref_image_paths,
            "size": size,
        },
        celery_task=generate_images_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "image_generation"}, "message": "ok"}
