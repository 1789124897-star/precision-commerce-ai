"""视频工作流路由 —— 参数校验 → 写 MySQL → 派发 Celery"""
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import save_upload
from app.models import Task
from app.schemas.video import (
    ComposeVideoRequest,
    ComposePremiumRequest,
    GenerateScriptRequest,
    GenerateShotRequest,
    GenerateTTSRequest,
)
from app.tasks.script_gen import script_gen_task
from app.tasks.tts_gen import tts_gen_task
from app.tasks.video import compose_video_task, compose_premium_task, generate_shot_task

router = APIRouter(prefix="/video", tags=["Video"])


# ── 口播脚本 ──

@router.post("/generate-script")
async def generate_script(body: GenerateScriptRequest, db: AsyncSession = Depends(get_db)) -> dict:
    task_id = uuid.uuid4().hex[:8]
    task = Task(
        task_id=task_id,
        type="script_gen",
        status="PENDING",
        request_json={
            "content": body.content,
            "target_segments": body.segments,
            "system_prompt": body.system_prompt,
        },
    )
    db.add(task)
    await db.commit()
    script_gen_task.delay(task_id=task_id)
    return {"data": {"task_id": task_id, "task_type": "script_generation"}, "message": "ok"}


# ── TTS 配音 ──

@router.post("/generate-tts")
async def generate_tts(body: GenerateTTSRequest, db: AsyncSession = Depends(get_db)) -> dict:
    task_id = uuid.uuid4().hex[:8]
    task = Task(
        task_id=task_id,
        type="tts_gen",
        status="PENDING",
        request_json={
            "script_path": body.script_path,
            "text": body.text,
            "voice": body.voice,
            "rate": body.rate,
        },
    )
    db.add(task)
    await db.commit()
    tts_gen_task.delay(task_id=task_id)
    return {"data": {"task_id": task_id, "task_type": "tts_generation"}, "message": "ok"}


# ── 素材上传 ──

@router.post("/upload-images")
async def upload_images(files: list[UploadFile] = File(...)) -> dict:
    return {"data": {"images": [save_upload(f, "img") for f in files]}, "message": "ok"}


@router.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)) -> dict:
    return {"data": {"audio_path": save_upload(file, "audio")}, "message": "ok"}


@router.post("/upload-srt")
async def upload_srt(file: UploadFile = File(...)) -> dict:
    return {"data": {"srt_path": save_upload(file, "srt")}, "message": "ok"}


# ── 视频合成 ──

@router.post("/compose")
async def compose_video(body: ComposeVideoRequest, db: AsyncSession = Depends(get_db)) -> dict:
    task_id = uuid.uuid4().hex[:8]
    task = Task(
        task_id=task_id,
        type="video_compose",
        status="PENDING",
        request_json={
            "image_urls": body.images,
            "audio_path": body.audio_path,
            "srt_path": body.srt_path,
            "aspect_ratio": body.aspect_ratio,
            "transition": body.transition or "fade",
            "quality_check": body.quality_check,
        },
    )
    db.add(task)
    await db.commit()
    compose_video_task.delay(task_id=task_id)
    return {"data": {"task_id": task_id, "task_type": "video_compose"}, "message": "ok"}


@router.post("/compose-premium")
async def compose_premium(body: ComposePremiumRequest, db: AsyncSession = Depends(get_db)) -> dict:
    task_id = uuid.uuid4().hex[:8]
    task = Task(
        task_id=task_id,
        type="video_compose",
        status="PENDING",
        request_json=body.model_dump(),
    )
    db.add(task)
    await db.commit()
    compose_premium_task.delay(task_id=task_id)
    return {"data": {"task_id": task_id, "task_type": "video_compose"}, "message": "ok"}


@router.post("/generate-shot")
async def generate_shot(body: GenerateShotRequest, db: AsyncSession = Depends(get_db)) -> dict:
    task_id = uuid.uuid4().hex[:8]
    task = Task(
        task_id=task_id,
        type="video_shot",
        status="PENDING",
        request_json=body.model_dump(),
    )
    db.add(task)
    await db.commit()
    generate_shot_task.delay(task_id=task_id)
    return {"data": {"task_id": task_id, "task_type": "video_shot"}, "message": "ok"}
