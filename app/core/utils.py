"""通用工具函数"""
import base64
import json
import re
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.exceptions import AppException
from app.core.paths import UPLOAD_DIR

_MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

_FILENAME_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|]')


def concise_api_error(service: str, status_code: int, body: str) -> str:
    """供应商 API 错误响应 → 一句简洁中文；完整原文请查日志。"""
    try:
        err = (json.loads(body or "{}").get("error") or {})
        code = str(err.get("code") or "")
        msg = str(err.get("message") or "")
    except (ValueError, TypeError):
        code, msg = "", ""
    if code == "AccountOverdueError" or "overdue balance" in msg.lower():
        return f"{service}账号欠费，请充值后重试"
    if "insufficient balance" in msg.lower():
        return f"{service}余额不足，请充值后重试"
    if msg:
        return f"{service}错误: {msg[:120]}"
    if code:
        return f"{service}错误[{code}]"
    return f"{service}错误 HTTP {status_code}"


def image_to_data_url(filepath: str) -> str:
    """本地图片文件 → base64 data URL。"""
    filename = Path(filepath).name
    p = UPLOAD_DIR / filename
    if not p.exists():
        raise AppException(f"图片不存在: {p}", 404)
    raw = p.read_bytes()
    mime = _MIME_MAP.get(p.suffix.lower(), "image/jpeg")
    encoded = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def save_upload(file: UploadFile, prefix: str) -> str:
    """保存上传文件到 uploads 目录，返回访问路径。"""
    suffix = Path(file.filename or "unknown").suffix
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}{suffix}"
    filepath = UPLOAD_DIR / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return f"/output/uploads/{filename}"


def sanitize_filename(name: str) -> str:
    """替换文件名中的非法字符为下划线。"""
    return _FILENAME_ILLEGAL_RE.sub("_", name)


def save_json(path: Path, data: object) -> None:
    """数据写入 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
