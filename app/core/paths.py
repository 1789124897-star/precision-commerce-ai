"""所有路径的单一来源 —— 输出目录 + 静态配置文件。

所有输出路径必须使用绝对路径，防止 uvicorn/Celery 不同 CWD 导致文件散落。
"""
from pathlib import Path

# 以本文件所在目录为基准推算项目根目录
# paths.py 在 app/core/ 下 → 往上两级即项目根
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

OUTPUT_DIR = _PROJECT_ROOT / "output"

VIDEO_DIR = OUTPUT_DIR / "videos"
AUDIO_DIR = OUTPUT_DIR / "audio"
IMAGE_DIR = OUTPUT_DIR / "images"
UPLOAD_DIR = OUTPUT_DIR / "uploads"
SCRIPT_DIR = OUTPUT_DIR / "scripts"

SCRAPER_CONFIG = _PROJECT_ROOT / "app" / "config" / "scraper_config.yaml"

for d in (VIDEO_DIR, AUDIO_DIR, IMAGE_DIR, UPLOAD_DIR, SCRIPT_DIR):
    d.mkdir(parents=True, exist_ok=True)
