"""1688 商品图片采集接口"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.task import TASK_TYPE_SCRAPE
from app.schemas.scraper import ScrapeRequest
from app.services.task_service import TaskService
from app.tasks.scraper import scrape_product_task

router = APIRouter(prefix="/scraper", tags=["Scraper"])


@router.post("/scrape")
async def do_scrape(payload: ScrapeRequest, db: AsyncSession = Depends(get_db)):
    task = await TaskService.create_and_dispatch(
        db,
        task_type=TASK_TYPE_SCRAPE,
        request_json={"url": payload.url},
        celery_task=scrape_product_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "scrape"}, "message": "ok"}
