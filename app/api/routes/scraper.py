"""1688 商品图片采集接口"""
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Task
from app.schemas.scraper import OpenFolderRequest, ScrapeRequest
from app.tasks.scraper import scrape_product_task

router = APIRouter(prefix="/scraper", tags=["Scraper"])


@router.post("/scrape")
async def do_scrape(payload: ScrapeRequest, db: AsyncSession = Depends(get_db)):
    task_id = uuid.uuid4().hex[:8]

    task = Task(
        task_id=task_id,
        type="scrape",
        status="PENDING",
        request_json={"url": payload.url},
    )
    db.add(task)
    await db.commit()

    scrape_product_task.delay(url=payload.url, task_id=task_id)

    return {"data": {"task_id": task_id, "task_type": "scrape"}, "message": "ok"}


@router.post("/open-folder")
def open_folder(payload: OpenFolderRequest):
    path = Path(payload.folder)
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"文件夹不存在: {payload.folder}")
    os.startfile(str(path))
    return {"data": {"ok": True}, "message": "ok"}
