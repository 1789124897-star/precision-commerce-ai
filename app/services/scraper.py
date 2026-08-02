"""1688 商品图抓取，DrissionPage 浏览器自动化。"""
import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Optional

import requests
import yaml
from DrissionPage import ChromiumOptions, ChromiumPage

from app.core.config import settings
from app.core.paths import IMAGE_DIR, SCRAPER_CONFIG
from app.services.anti_crawl import (
    ensure_fresh_cookies,
    load_cookies,
    random_delay,
    save_cookies,
)
from app.services.proxy_manager import ProxyManager

logger = logging.getLogger(__name__)

with open(SCRAPER_CONFIG, encoding="utf-8") as f:
    SCRAPER_CFG = yaml.safe_load(f)

_IMG_PREFIX = {"main": "主图", "sku": "SKU", "detail": "详情图"}


class ImageScraper:

    def __init__(self):

        self.images: list[dict] = []
        self._proxy: str = ""
        self.proxy_manager = ProxyManager(
            settings.PROXY_PROVIDER,
            settings.PROXY_HOST,
            settings.PROXY_PORT,
            settings.PROXY_USERNAME,
            settings.PROXY_PASSWORD,
        )

    # ── 主入口 ────────────────────────────────────────────

    def scrape(self, product_url: str, task_id: str) -> dict:
        task_dir = IMAGE_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        logger.info("开始采集 %s -> %s", task_id, task_dir)

        self.images = []
        product_name = self._collect(task_dir, product_url)

        if not self.images:
            raise RuntimeError("未采集到任何图片，页面结构可能已变更或触发反爬")

        metadata = self._build_metadata(task_id, product_name, product_url)
        meta_path = task_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("元数据已保存: %s", meta_path)

        return {
            "task_id": task_id,
            "name": product_name,
            "folder": str(task_dir.resolve()).replace("\\", "/"),
            "image_count": len(self.images),
            "images": metadata,
        }

    # ── 浏览器采集流程 ────────────────────────────────────

    def _collect(self, task_dir: Path, product_url: str) -> str:
        """打开浏览器，执行完整采集流程，返回商品名。"""
        options = ChromiumOptions()
        options.set_browser_path(settings.EDGE_PATH)

        self._proxy = self.proxy_manager.get_next()
        if self._proxy:
            options.set_proxy(self._proxy)

        page = ChromiumPage(options)
        try:
            ensure_fresh_cookies(page, settings.ALIBABA_1688_EMAIL, settings.ALIBABA_1688_PASSWORD)
            load_cookies(page)

            page.get(product_url)
            random_delay()
            product_name = self._parse_title(page.title or "")

            version = self._detect_version(page)
            logger.info("页面: %s | 版本: %s", product_name, version.upper())

            self._download_images(page, task_dir, version, "main_image", "main")
            random_delay(1.0, 2.0)
            self._scroll_to_bottom(page)
            random_delay(1.0, 2.0)
            self._download_sku_images(page, task_dir, version)
            random_delay(1.0, 2.0)
            self._download_images(page, task_dir, version, "detail_image", "detail")

            return product_name
        except Exception:
            logger.exception("采集失败")
            if not self.images:
                shutil.rmtree(task_dir, ignore_errors=True)
            raise
        finally:
            save_cookies(page)
            page.quit()

    @staticmethod
    def _parse_title(title: str) -> str:
        """从 1688 页面标题中提取商品名。"""
        for sep in ("-阿里巴巴", "- 阿里巴巴", "-1688", "- 1688", "| 1688"):
            if sep in title:
                return title.split(sep)[0].strip()
        return title

    @staticmethod
    def _detect_version(page) -> str:
        """根据页面元素命中情况判断 1688 页面版本。"""
        for v in ("v3", "v2"):
            if page.ele(SCRAPER_CFG["selectors"][v]["main_image"]):
                return v
        return "v1"

    # ── 图片下载 ──────────────────────────────────────────

    def _download_images(self, page, task_dir: Path, version: str, selector_key: str, category: str) -> None:
        """下载主图/详情图（按选择器取元素 → 提取 URL → 去重 → 下载）。"""
        cfg = SCRAPER_CFG["selectors"][version]
        elements = page.eles(cfg[selector_key])
        attrs = ("src", "data-lazyload-src") if version == "v1" else ("src",)
        prefix = _IMG_PREFIX[category]

        logger.info("发现 %d 张%s", len(elements), prefix)
        seen: set[str] = set()
        for idx, el in enumerate(elements, 1):
            try:
                url = next((el.attr(a) for a in attrs if el.attr(a)), None)
                if not url or url in seen:
                    continue
                seen.add(url)
                filename = f"{prefix}_{idx}.jpg"
                if self._download(url, task_dir, filename):
                    self.images.append(
                        {"filename": filename, "url": url, "category": category}
                    )
            except Exception:
                logger.warning("%s_%d 处理异常", prefix, idx, exc_info=True)

    def _download_sku_images(self, page, task_dir: Path, version: str) -> None:
        """下载 SKU 变体图（URL 可能来自背景图，需提取标签，去除 _sum 后缀）。"""
        cfg = SCRAPER_CFG["selectors"][version]
        nodes = page.eles(cfg["sku_image"])
        prefix = _IMG_PREFIX["sku"]

        logger.info("发现 %d 张%s", len(nodes), prefix)
        seen: set[str] = set()
        for idx, node in enumerate(nodes, 1):
            try:
                url = node.attr("src") or self._extract_bg_url(node.attr("style"))
                if not url or url in seen:
                    continue
                seen.add(url)
                url = url.replace("_sum.jpg", "").replace("_sum.webp", "")

                label = self._extract_sku_label(node, cfg)
                safe_label = (
                    re.sub(r'[\\/:*?"<>|]', "_", label) if label else str(idx)
                )
                filename = f"{prefix}_{idx}_{safe_label}.jpg"
                if self._download(url, task_dir, filename):
                    entry = {"filename": filename, "url": url, "category": "sku"}
                    if label:
                        entry["label"] = label
                    self.images.append(entry)
            except Exception:
                logger.warning("%s_%d 处理异常", prefix, idx, exc_info=True)

    def _extract_sku_label(self, node, cfg: dict) -> str:
        """向上遍历 DOM，提取 SKU 规格标签。"""
        try:
            ancestor = node
            for _ in range(cfg["sku_label_level"]):
                p = ancestor.parent
                ancestor = p() if callable(p) else p
            el = ancestor.ele(cfg["sku_label"])
            return el.text.strip() if el else ""
        except Exception:
            logger.warning("SKU 标签提取异常", exc_info=True)
            return ""

    @staticmethod
    def _scroll_to_bottom(page) -> None:
        """滚动到底部触发懒加载。"""
        try:
            start = time.time()
            last = page.run_js("return document.body.scrollHeight;")
            while time.time() - start < SCRAPER_CFG["download"]["scroll_timeout"]:
                page.scroll.to_bottom()
                random_delay(0.5, 1.0)
                cur = page.run_js("return document.body.scrollHeight;")
                if cur == last:
                    break
                last = cur
            logger.info("已滚动到页面底部")
        except Exception:
            logger.warning("滚动异常，跳过", exc_info=True)

    # ── 底层：单张下载 & 工具 ──────────────────────────────

    def _download(self, url: str, save_dir: Path, filename: str) -> bool:
        """下载单张图片，过滤过小/非图片响应。"""
        filename = re.sub(r'[\\/:*?"<>|]', "_", filename)
        try:
            proxy = self._proxy
            proxies = {"http": proxy, "https": proxy} if proxy else {"http": "", "https": ""}
            resp = requests.get(
                url,
                stream=True,
                timeout=SCRAPER_CFG["download"]["timeout"],
                headers=SCRAPER_CFG["request"]["headers"],
                proxies=proxies,
            )
            resp.raise_for_status()
            if "text/html" in resp.headers.get("Content-Type", ""):
                logger.warning("%s 返回 HTML，跳过", filename)
                return False
            filepath = save_dir / filename
            filepath.write_bytes(resp.content)
            size = filepath.stat().st_size
            if size < SCRAPER_CFG["download"]["min_bytes"]:
                filepath.unlink()
                logger.warning("%s 过小 (%dB)，已删除", filename, size)
                return False
            logger.info("下载成功: %s (%dB)", filename, size)
            return True
        except requests.RequestException:
            logger.warning("下载失败: %s", filename, exc_info=True)
            return False

    @staticmethod
    def _extract_bg_url(style: Optional[str]) -> Optional[str]:
        """从 CSS background-image 中提取 URL。"""
        if not style:
            return None
        m = re.search(r'url\(["\']?(.*?)["\']?\)', style)
        return m.group(1) if m else None

    def _build_metadata(self, task_id: str, product_name: str, product_url: str) -> dict:
        return {
            "task_id": task_id,
            "product_name": product_name,
            "product_url": product_url,
            "main_images": [i for i in self.images if i["category"] == "main"],
            "sku_images": [i for i in self.images if i["category"] == "sku"],
            "detail_images": [i for i in self.images if i["category"] == "detail"],
        }
