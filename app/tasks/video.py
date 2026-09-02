"""视频合成 / 精铺 / 分镜 Celery 任务"""
import logging

from app.core.celery_app import celery_app
from app.core.database import SyncSession
from app.core.exceptions import AppException
from app.core.paths import to_output_url
from app.models import Video
from app.models.task import STATUS_SUCCESS
from app.repositories.task_repo import TaskRepo
from app.services.premium_video_composer import PremiumVideoComposer
from app.services.quick_video_composer import QuickVideoComposer
from app.services.shot_service import ShotService

logger = logging.getLogger(__name__)


def _progress_callback(task_id: str):
    """返回 on_progress(pct, stage) 回调 → 节流写入 MySQL 供前端轮询"""
    import time

    _last_ts = [0.0]

    def on_progress(pct: float, stage: str):
        now = time.monotonic()
        if now - _last_ts[0] < 1.0:
            return
        _last_ts[0] = now
        try:
            with SyncSession() as db:
                TaskRepo.set_result(db, task_id, {"progress": round(pct, 3), "stage": stage})
                db.commit()
        except Exception:
            logger.exception("写入进度失败")

    return on_progress


@celery_app.task(
    bind=True,
    name="compose_video",
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
            logger.error("任务不存在 task_id=%s", task_id)
            return {"task_id": task_id, "status": "NOT_FOUND"}
        request_json = task.request_json or {}
        db.commit()

    try:
        result = QuickVideoComposer().compose(**request_json, task_id=task_id, on_progress=_progress_callback(task_id))
    except AppException as e:
        logger.error("业务失败 task_id=%s: %s", task_id, e.message)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, e.message)
            db.commit()
        return {"task_id": task_id, "status": "FAILURE"}
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
                    source_images=str(request_json.get("images", [])),
                    audio_path=request_json.get("audio_path", ""),
                    srt_path=request_json.get("srt_path", ""),
                    output_path=result.get("video_path", ""),
                    duration_sec=result.get("duration_sec", 0),
                    aspect_ratio=request_json.get("aspect_ratio", "9:16"),
                )
            )
        db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"task_id": task_id, "status": STATUS_SUCCESS}


@celery_app.task(
    bind=True,
    name="compose_premium_video",
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
            logger.error("任务不存在 task_id=%s", task_id)
            return {"task_id": task_id, "status": "NOT_FOUND"}
        request_json = task.request_json or {}
        db.commit()

    try:
        result = PremiumVideoComposer().compose_premium(**request_json, task_id=task_id, on_progress=_progress_callback(task_id))
    except AppException as e:
        logger.error("业务失败 task_id=%s: %s", task_id, e.message)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, e.message)
            db.commit()
        return {"task_id": task_id, "status": "FAILURE"}
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
                    source_images=str([s.get("clip_path", "") for s in request_json.get("shots", [])]),
                    audio_path=request_json.get("audio_path", ""),
                    srt_path=request_json.get("srt_path", ""),
                    output_path=result.get("video_path", ""),
                    duration_sec=result.get("duration_sec", 0),
                )
            )
        db.commit()

    logger.info("完成 task_id=%s", task_id)
    return {"task_id": task_id, "status": STATUS_SUCCESS}


@celery_app.task(
    bind=True,
    name="generate_shot",
    soft_time_limit=300,
    time_limit=420,
)
def generate_shot_task(self, task_id: str):

    logger.info("开始 task_id=%s", task_id)
    
    with SyncSession() as db:
        task = TaskRepo.set_running(db, task_id, self.request.id)
        if not task:
            logger.error("任务不存在 task_id=%s", task_id)
            return {"task_id": task_id, "status": "NOT_FOUND"}
        request_json = task.request_json or {}
        db.commit()

    try:
        cb = _progress_callback(task_id)
        clip_path = ShotService().run_sync(**request_json, on_progress=lambda stage, detail: cb(0, f"{stage}: {detail}"))
    except AppException as e:
        logger.error("业务失败 task_id=%s: %s", task_id, e.message)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, e.message)
            db.commit()
        return {"task_id": task_id, "status": "FAILURE"}
    except Exception as e:
        logger.exception("失败 task_id=%s", task_id)
        with SyncSession() as db:
            TaskRepo.set_failure(db, task_id, str(e))
            db.commit()
        raise

    video_path = to_output_url(clip_path)

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
    return {"task_id": task_id, "status": STATUS_SUCCESS}
