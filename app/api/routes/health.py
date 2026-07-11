"""健康检查"""
from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    return {"data": {"status": "ok"}, "message": "ok"}
