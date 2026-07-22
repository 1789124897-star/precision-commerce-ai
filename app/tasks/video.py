"""视频合成 / 精铺 / 分镜 Celery 任务"""
import logging

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.models import Video
from app.repositories.task_repo import TaskRepo
from app.services.seedance_service import SeedanceService
from app.services.video_composer import composer

logger = logging.getLogger(__name__)


def _progress_callback(task_id: str):
    """返回 on_progress(pct, stage) 回调 → 写入 MySQL 供前端轮询

    内置节流：最多每秒写入一次，避免编码期间每帧都触发 DB 事务。
    """
    import time

    _last_ts = [0.0]

    def on_progress(pct: float, stage: str):
        now = time.monotonic()
        if now - _last_ts[0] < 1.0:
            return
        _last_ts[0] = now
        try:
            with SyncSession() as db:
                TaskRepo.set_result(
                    db, task_id, {"progress": round(pct, 3), "stage": stage}
                )
                db.commit()
        except Exception:
            logger.exception("写入进度失败")

    return on_progress


@celery_app.task(
    bind=True,
    name="compose_video",
    priority=3,
    soft_time_limit=600,
    time_limit=900,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def compose_video_task(self, task_id: str):
    logger.info("开始 task_id=%s", task_id)
    with SyncSession() as db:
        task = TaskRepo.set_running(db, task_id, self.request.id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        request_json = dict(task.request_json or {})
        db.commit()

    try:
        result = composer.compose(
            image_urls=request_json.get("image_urls", []),
            audio_path=request_json.get("audio_path", ""),
            srt_path=request_json.get("srt_path", ""),
            task_id=task_id,
            aspect_ratio=request_json.get("aspect_ratio", "9:16"),
            transition=request_json.get("transition", "fade"),
            quality_check=request_json.get("quality_check", True),
            on_progress=_progress_callback(task_id),
        )
    except Exception as e:
        logger.exception("失败 task_id=%s", task_id)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, str(e))
            db.commit()
        raise

    with SyncSession() as db:
        task = TaskRepo.set_success(db, task_id, result)
        if task:
            db.add(
                Video(
                    task_id=task_id,
                    video_type="compose",
                    source_images=str(request_json.get("image_urls", [])),
                    audio_path=request_json.get("audio_path", ""),
                    srt_path=request_json.get("srt_path", ""),
                    output_path=result.get("video_path", ""),
                    duration_sec=result.get("duration_sec", 0),
                    aspect_ratio=request_json.get("aspect_ratio", "9:16"),
                )
            )
        db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"task_id": task_id, "status": "SUCCESS"}


@celery_app.task(
    bind=True,
    name="compose_premium_video",
    priority=3,
    soft_time_limit=600,
    time_limit=900,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def compose_premium_video_task(self, task_id: str):
    logger.info("开始 task_id=%s", task_id)
    with SyncSession() as db:
        task = TaskRepo.set_running(db, task_id, self.request.id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        request_json = dict(task.request_json or {})
        db.commit()

    try:
        result = composer.compose_premium(
            shots=request_json.get("shots", []),
            images=request_json.get("images", []),
            audio_path=request_json.get("audio_path", ""),
            srt_path=request_json.get("srt_path", ""),
            task_id=task_id,
            aspect_ratio=request_json.get("aspect_ratio", "9:16"),
            generate_audio=request_json.get("generate_audio", False),
            on_progress=_progress_callback(task_id),
            segment_durations=request_json.get("segment_durations"),
        )
    except Exception as e:
        logger.exception("失败 task_id=%s", task_id)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, str(e))
            db.commit()
        raise

    with SyncSession() as db:
        task = TaskRepo.set_success(db, task_id, result)
        if task:
            db.add(
                Video(
                    task_id=task_id,
                    video_type="compose_premium",
                    source_images=str(request_json.get("images", [])),
                    audio_path=request_json.get("audio_path", ""),
                    srt_path=request_json.get("srt_path", ""),
                    output_path=result.get("video_path", ""),
                    duration_sec=result.get("duration_sec", 0),
                    aspect_ratio=request_json.get("aspect_ratio", "9:16"),
                    resolution=request_json.get("resolution", ""),
                )
            )
        db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"task_id": task_id, "status": "SUCCESS"}


@celery_app.task(
    bind=True,
    name="generate_shot",
    priority=3,
    soft_time_limit=300,
    time_limit=420,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    retry_jitter=True,
)
def generate_shot_task(self, task_id: str):
    logger.info("开始 task_id=%s", task_id)
    with SyncSession() as db:
        task = TaskRepo.set_running(db, task_id, self.request.id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        request_json = dict(task.request_json or {})
        db.commit()

    def shot_progress(stage: str, detail: str):
        try:
            with SyncSession() as db:
                TaskRepo.set_result(db, task_id, {"stage": stage, "detail": detail})
                db.commit()
        except Exception:
            logger.exception("写入分镜进度失败")

    try:
        clip_path = SeedanceService().generate_shot_sync(
            image_url=request_json.get("image_url", ""),
            first_frame_url=request_json.get("first_frame_url", ""),
            last_frame_url=request_json.get("last_frame_url", ""),
            prompt=request_json.get("scene_prompt", ""),
            aspect_ratio=request_json.get("aspect_ratio", "9:16"),
            duration_sec=request_json.get("duration_sec", 5.0),
            shot_index=request_json.get("shot_index", 0),
            on_progress=shot_progress,
            generate_audio=request_json.get("generate_audio", False),
            resolution=request_json.get("resolution", "720p"),
        )
        video_path = "/" + str(clip_path).replace("\\", "/")
    except Exception as e:
        logger.exception("失败 task_id=%s", task_id)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, str(e))
            db.commit()
        raise

    with SyncSession() as db:
        TaskRepo.set_success(
            db,
            task_id,
            {
                "status": "complete",
                "video_path": video_path,
                "shot_index": request_json.get("shot_index", 0),
            },
        )
        db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"task_id": task_id, "status": "SUCCESS"}
