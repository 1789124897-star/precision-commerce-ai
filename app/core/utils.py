"""通用工具函数"""
import base64
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.paths import UPLOAD_DIR

_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def image_to_data_url(filepath: str) -> str:
    """读取本地图片文件，转为 base64 data URL。"""
    filename = Path(filepath).name
    p = UPLOAD_DIR / filename
    if not p.exists():
        raise FileNotFoundError(f"图片不存在: {p}")
    raw = p.read_bytes()
    mime = _MIME_MAP.get(p.suffix.lower(), "image/jpeg")
    encoded = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def save_upload(file: UploadFile, prefix: str) -> str:

    filepath = UPLOAD_DIR / f"{prefix}_{uuid.uuid4().hex[:8]}{Path(file.filename or 'unknown').suffix}"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return "/output/uploads/" + filepath.name
