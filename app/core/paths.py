"""所有路径的单一来源 —— 输出目录 + 静态配置文件。"""
from pathlib import Path

OUTPUT_DIR = Path("output")

VIDEO_DIR = OUTPUT_DIR / "videos"
AUDIO_DIR = OUTPUT_DIR / "audio"
IMAGE_DIR = OUTPUT_DIR / "images"
UPLOAD_DIR = OUTPUT_DIR / "uploads"
SCRIPT_DIR = OUTPUT_DIR / "scripts"

SCRAPER_CONFIG = Path(__file__).resolve().parent.parent / "config" / "scraper_config.yaml"

for dir in (VIDEO_DIR, AUDIO_DIR, IMAGE_DIR, UPLOAD_DIR, SCRIPT_DIR):
    dir.mkdir(parents=True, exist_ok=True)
