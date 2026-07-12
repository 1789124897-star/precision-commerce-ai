import logging

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.models import Video
from app.repositories.task_repo import TaskRepo
from app.services.seedance_service import SeedanceService
from app.services.video_composer import composer

logger = logging.getLogger(__name__)


def _progress_callback(task_id: str):
    """返回 on_progress(pct, stage) 回调 → 写入 MySQL 供前端轮询"""

    def on_progress(pct: float, stage: str):
        try:
            with SyncSession() as db:
                task = TaskRepo.get_by_id(db, task_id)
                if task:
                    task.result_json = {"progress": round(pct, 3), "stage": stage}
                    db.commit()
        except Exception:
            logger.exception("写入进度失败")

    return on_progress


@celery_app.task(
    bind=True,
    name="compose_video",
    priority=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def compose_video_task(self, task_id: str):
    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "RUNNING"
            task.celery_id = self.request.id
            db.commit()

    try:
        result = composer.compose(
            image_urls=task.request_json.get("image_urls", []),
            audio_path=task.request_json.get("audio_path", ""),
            srt_path=task.request_json.get("srt_path", ""),
            task_id=task_id,
            aspect_ratio=task.request_json.get("aspect_ratio", "9:16"),
            transition=task.request_json.get("transition", "fade"),
            quality_check=task.request_json.get("quality_check", True),
            on_progress=_progress_callback(task_id),
        )
    except Exception as e:
        with SyncSession() as db:
            task = TaskRepo.get_by_id(db, task_id)
            if task:
                task.status = "FAILURE"
                task.error_message = str(e)
                db.commit()
        raise

    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "SUCCESS"
            task.result_json = result
        kwargs = task.request_json or {}
        db.add(Video(
            task_id=task_id,
            video_type="compose",
            source_images=str(kwargs.get("image_urls", [])),
            audio_path=kwargs.get("audio_path", ""),
            srt_path=kwargs.get("srt_path", ""),
            output_path=result.get("video_path", ""),
            duration_sec=result.get("duration_sec", 0),
            aspect_ratio=kwargs.get("aspect_ratio", "9:16"),
        ))
        db.commit()

    return {"task_id": task_id, "status": "SUCCESS"}


@celery_app.task(
    bind=True,
    name="compose_premium_video",
    priority=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def compose_premium_task(self, task_id: str):
    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "RUNNING"
            task.celery_id = self.request.id
            db.commit()

    try:
        result = composer.compose_premium(
            shots=task.request_json.get("shots", []),
            images=task.request_json.get("images", []),
            audio_path=task.request_json.get("audio_path", ""),
            srt_path=task.request_json.get("srt_path", ""),
            task_id=task_id,
            aspect_ratio=task.request_json.get("aspect_ratio", "9:16"),
            generate_audio=task.request_json.get("generate_audio", False),
            on_progress=_progress_callback(task_id),
        )
    except Exception as e:
        with SyncSession() as db:
            task = TaskRepo.get_by_id(db, task_id)
            if task:
                task.status = "FAILURE"
                task.error_message = str(e)
                db.commit()
        raise

    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "SUCCESS"
            task.result_json = result
        kwargs = task.request_json or {}
        db.add(Video(
            task_id=task_id,
            video_type="compose_premium",
            source_images=str(kwargs.get("images", [])),
            audio_path=kwargs.get("audio_path", ""),
            srt_path=kwargs.get("srt_path", ""),
            output_path=result.get("video_path", ""),
            duration_sec=result.get("duration_sec", 0),
            aspect_ratio=kwargs.get("aspect_ratio", "9:16"),
            resolution=kwargs.get("resolution", ""),
        ))
        db.commit()

    return {"task_id": task_id, "status": "SUCCESS"}


@celery_app.task(
    bind=True,
    name="generate_shot",
    priority=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def generate_shot_task(self, task_id: str):
    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "RUNNING"
            task.celery_id = self.request.id
            db.commit()

    req = task.request_json or {}

    def shot_progress(stage: str, detail: str):
        try:
            with SyncSession() as db:
                task = TaskRepo.get_by_id(db, task_id)
                if task:
                    task.result_json = {"stage": stage, "detail": detail}
                    db.commit()
        except Exception:
            logger.exception("写入分镜进度失败")

    try:
        clip_path = SeedanceService().generate_shot_sync(
            image_url=req.get("image_url", ""),
            first_frame_url=req.get("first_frame_url", ""),
            last_frame_url=req.get("last_frame_url", ""),
            prompt=req.get("scene_prompt", ""),
            aspect_ratio=req.get("aspect_ratio", "9:16"),
            duration_sec=req.get("duration_sec", 5.0),
            shot_index=req.get("shot_index", 0),
            on_progress=shot_progress,
            generate_audio=req.get("generate_audio", False),
            resolution=req.get("resolution", "720p"),
        )
        video_path = "/" + str(clip_path).replace("\\", "/")
    except Exception as e:
        with SyncSession() as db:
            task = TaskRepo.get_by_id(db, task_id)
            if task:
                task.status = "FAILURE"
                task.error_message = str(e)
                db.commit()
        raise

    with SyncSession() as db:
        task = TaskRepo.get_by_id(db, task_id)
        if task:
            task.status = "SUCCESS"
            task.result_json = {
                "status": "complete",
                "video_path": video_path,
                "shot_index": req.get("shot_index", 0),
            }
        db.commit()

    return {"task_id": task_id, "status": "SUCCESS"}
