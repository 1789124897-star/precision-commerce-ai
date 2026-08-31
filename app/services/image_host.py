"""本地图片公网化 — cloudflared 快速隧道

参照 jlc-global-ozon-auto-listing 的 CloudflareImageTunnel 简化移植：
本地起静态 HTTP 服务 → cloudflared quick tunnel → 公网 URL。
懒启动 + 全局复用 + 失效自动重建，Seedance 提交前自动转换本地路径。
"""
import http.server
import logging
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.paths import OUTPUT_DIR

logger = logging.getLogger(__name__)


class ImageTunnelError(RuntimeError):
    pass


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


CLOUDFLARED_FALLBACK_PATHS = (
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\Program Files\cloudflared\cloudflared.exe",
    "/opt/homebrew/bin/cloudflared",
    "/usr/local/bin/cloudflared",
)


def resolve_cloudflared_binary() -> str:
    """按 CLOUDFLARED_BIN → PATH → 常见安装路径 顺序查找 cloudflared。"""
    configured = str(settings.CLOUDFLARED_BIN or os.environ.get("CLOUDFLARED_BIN") or "").strip()
    candidates = [configured] if configured else []
    found = shutil.which("cloudflared")
    if found:
        candidates.append(found)
    candidates.extend(CLOUDFLARED_FALLBACK_PATHS)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise ImageTunnelError(
        "cloudflared 未安装或不可用；已检查 CLOUDFLARED_BIN、PATH 及常见安装路径"
    )


class ImageHost:
    """本地图片公网化：本地静态服务 + cloudflared quick tunnel。"""

    URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

    def __init__(self, directory: Path = OUTPUT_DIR):
        self.directory = directory.resolve()
        self.server: Optional[http.server.ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.process: Optional[subprocess.Popen[str]] = None
        self.public_url: Optional[str] = None

    # ── 生命周期 ──

    def start(self) -> str:
        """启动隧道，返回公网根 URL；已运行时直接复用。"""
        if self.is_alive():
            return self.public_url
        self.stop()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        handler = lambda *args, **kwargs: _QuietHandler(  # noqa: E731
            *args, directory=str(self.directory), **kwargs
        )
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        cloudflared = resolve_cloudflared_binary()
        self.process = subprocess.Popen(
            [
                cloudflared, "tunnel", "--url", f"http://127.0.0.1:{port}",
                "--no-autoupdate", "--protocol", "http2",
                "--edge-ip-version", "4",  # 国内 IPv6 到 Cloudflare 常不通，强制 IPv4 避免长时间空等
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # Windows 上 select 不支持子进程管道，改用独立线程逐行读 stdout
        url_ready = threading.Event()
        tunnel_ready = threading.Event()
        found_url: dict[str, str] = {}

        def _reader() -> None:
            assert self.process is not None and self.process.stdout is not None
            for line in self.process.stdout:
                match = self.URL_PATTERN.search(line)
                if match:
                    found_url["url"] = match.group(0)
                    url_ready.set()
                if "Registered tunnel connection" in line:
                    tunnel_ready.set()

        threading.Thread(target=_reader, daemon=True).start()

        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise ImageTunnelError("cloudflared 在创建隧道前已退出")
            if url_ready.is_set() and tunnel_ready.is_set():
                self.public_url = found_url["url"]
                logger.info(f"图床隧道已就绪: {self.public_url} (服务 {self.directory})")
                return self.public_url
            time.sleep(0.2)
        raise ImageTunnelError("等待 cloudflared 隧道连接超时 (45s)")

    def is_alive(self) -> bool:
        """隧道进程与本地服务均存活即视为可用。"""
        return bool(
            self.public_url
            and self.process is not None and self.process.poll() is None
            and self.server is not None
        )

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except OSError:
                pass
        self.process = self.server = self.thread = None
        self.public_url = None

    # ── URL 转换 ──

    def to_public(self, url_or_path: str) -> str:
        """本地路径/本地 URL → 公网 URL；外网 URL 原样返回。"""
        value = str(url_or_path or "").strip()
        if not value:
            return value
        if value.startswith(("https://", "http://")):
            parsed = urllib.parse.urlparse(value)
            if parsed.hostname in {"localhost", "127.0.0.1", "::1"} and parsed.path.startswith("/output/"):
                value = parsed.path  # localhost 指向本机 /output，解析出相对路径
            else:
                return value  # 外网 URL 原样透传
        if value.startswith("/output/"):
            rel = value[len("/output/"):]
            local = self.directory / rel
            if not local.is_file():
                raise ImageTunnelError(f"本地图片不存在: {local}")
            return f"{self.start()}/{urllib.parse.quote(rel, safe='/')}"
        local = Path(value)
        if local.is_absolute() and local.is_file():
            try:
                rel = local.relative_to(self.directory)
            except ValueError:
                raise ImageTunnelError(f"图片不在图床目录内: {local}")
            return f"{self.start()}/{urllib.parse.quote(str(rel).replace(os.sep, '/'), safe='/')}"
        return value


# 全局单例：懒启动，后端进程内复用
image_host = ImageHost()
