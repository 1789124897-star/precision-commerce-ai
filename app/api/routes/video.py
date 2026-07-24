"""视频工作流路由 —— 参数校验 → TaskService 建任务并下发"""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import save_upload
from app.schemas.video import (
    ComposePremiumRequest,
    ComposeVideoRequest,
    GenerateScriptRequest,
    GenerateShotRequest,
    GenerateTTSRequest,
)
from app.services.task_service import TaskService
from app.tasks.script_gen import generate_script_task
from app.tasks.tts_gen import generate_tts_task
from app.tasks.video import compose_premium_video_task, compose_video_task, generate_shot_task

router = APIRouter(prefix="/video", tags=["Video"])


@router.post("/generate-script")
async def generate_script(body: GenerateScriptRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """AI 生成口播脚本，按目标段数拆分。"""
    task = await TaskService.create_and_dispatch(
        db,
        task_type="script_gen",
        request_json={
            "content": body.content,
            "target_segments": body.segments,
            "system_prompt": body.system_prompt,
            "tts_rate": body.tts_rate,
        },
        celery_task=generate_script_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "script_generation"}, "message": "ok"}


@router.post("/generate-tts")
async def generate_tts(body: GenerateTTSRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """TTS 配音：将脚本文本转为音频 + SRT 字幕。"""
    task = await TaskService.create_and_dispatch(
        db,
        task_type="tts_gen",
        request_json={
            "script_path": body.script_path,
            "text": body.text,
            "voice": body.voice,
            "rate": body.rate,
        },
        celery_task=generate_tts_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "tts_generation"}, "message": "ok"}


@router.post("/upload-images")
async def upload_images(files: list[UploadFile] = File(...)) -> dict:
    """上传图片素材，返回服务端存储路径。"""
    return {"data": {"images": [save_upload(f, "img") for f in files]}, "message": "ok"}


@router.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)) -> dict:
    """上传外部音频文件。"""
    return {"data": {"audio_path": save_upload(file, "audio")}, "message": "ok"}


@router.post("/upload-srt")
async def upload_srt(file: UploadFile = File(...)) -> dict:
    """上传外部 SRT 字幕文件。"""
    return {"data": {"srt_path": save_upload(file, "srt")}, "message": "ok"}


@router.post("/compose")
async def compose_video(body: ComposeVideoRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """基础合成：图片 + 音频 + 字幕 → MP4。"""
    task = await TaskService.create_and_dispatch(
        db,
        task_type="video_compose",
        request_json={
            "image_urls": body.images,
            "audio_path": body.audio_path,
            "srt_path": body.srt_path,
            "aspect_ratio": body.aspect_ratio,
            "transition": body.transition or "fade",
            "quality_check": body.quality_check,
        },
        celery_task=compose_video_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "video_compose"}, "message": "ok"}


@router.post("/compose-premium")
async def compose_premium(body: ComposePremiumRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """精铺合成：分镜编排 + 文案叠加 + 转场特效。"""
    task = await TaskService.create_and_dispatch(
        db,
        task_type="video_compose",
        request_json=body.model_dump(),
        celery_task=compose_premium_video_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "video_compose"}, "message": "ok"}


@router.post("/generate-shot")
async def generate_shot(body: GenerateShotRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """AI 分镜生成：根据脚本自动编排图片序列。"""
    task = await TaskService.create_and_dispatch(
        db,
        type="shot_gen",
        request_json=body.model_dump(),
        celery_task=generate_shot_task,
    )
    return {"data": {"task_id": task.task_id, "task_type": "shot_gen"}, "message": "ok"}
