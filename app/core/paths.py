"""全局路径管理"""
from pathlib import Path

# 根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

OUTPUT_DIR = _PROJECT_ROOT / "output"

VIDEO_DIR = OUTPUT_DIR / "videos"
AUDIO_DIR = OUTPUT_DIR / "audio"
IMAGE_DIR = OUTPUT_DIR / "images"
UPLOAD_DIR = OUTPUT_DIR / "uploads"
SCRIPTS_DIR = OUTPUT_DIR / "scripts"

SCRAPER_CONFIG = _PROJECT_ROOT / "app" / "config" / "scraper_config.yaml"

for d in (VIDEO_DIR, AUDIO_DIR, IMAGE_DIR, UPLOAD_DIR, SCRIPTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def to_output_url(path: Path) -> str:
    """本地绝对路径 → /output/ URL。"""
    return "/output/" + str(path.relative_to(OUTPUT_DIR)).replace("\\", "/")


def from_output_url(url_or_path: str) -> Path:
    """/output/ URL 或普通路径 → 本地绝对路径。"""
    if url_or_path.startswith("/output/"):
        return OUTPUT_DIR / url_or_path[len("/output/"):]
    return Path(url_or_path)
