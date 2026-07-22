"""1688 商品图片采集接口"""
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.scraper import OpenFolderRequest, ScrapeRequest
from app.services.task_service import TaskService
from app.tasks.scraper import scrape_product_task

router = APIRouter(prefix="/scraper", tags=["Scraper"])


@router.post("/scrape")
async def do_scrape(payload: ScrapeRequest, db: AsyncSession = Depends(get_db)):
    task = await TaskService.create_and_dispatch(
        db,
        task_type="scrape",
        request_json={"url": payload.url},
        celery_task=scrape_product_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "scrape"}, "message": "ok"}


@router.post("/open-folder")
def open_folder(payload: OpenFolderRequest):
    path = Path(payload.folder)
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"文件夹不存在: {payload.folder}")
    os.startfile(str(path))
    return {"data": {"ok": True}, "message": "ok"}
