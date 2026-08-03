"""SRT 字幕时间格式转换工具"""


def seconds_to_srt(seconds: float) -> str:
    """秒 → SRT 时间戳 HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_to_seconds(timestamp: str) -> float:
    """SRT 时间戳 HH:MM:SS,mmm → 秒"""
    h, m, rest = timestamp.split(":")
    s, ms = rest.split(",") if "," in rest else (rest, "0")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
