"""1688 商品图抓取，DrissionPage浏览器自动化。"""

import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Optional, List

import requests
import yaml
from DrissionPage import ChromiumOptions, ChromiumPage

from app.core.config import settings
from app.core.paths import IMAGE_DIR as OUTPUT_ROOT, SCRAPER_CONFIG

logger = logging.getLogger(__name__)

with open(SCRAPER_CONFIG, "r", encoding="utf-8") as f:
    SCRAPER_CFG = yaml.safe_load(f)


class ImageScraper:

    def __init__(self):
        self.images: List[dict] = []

    def scrape(self, product_url: str, task_id: str) -> dict:
        task_dir = OUTPUT_ROOT / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        logger.info("开始采集 %s -> %s", task_id, task_dir)

        options = ChromiumOptions()
        options.set_browser_path(settings.EDGE_PATH)
        page = ChromiumPage(options)

        try:
            page.get(product_url)
            time.sleep(2)
            logger.info("页面标题: %s", page.title)

            product_name = page.title or ""
            for suffix in ["-阿里巴巴", "- 阿里巴巴", "-1688", "- 1688", "| 1688"]:
                if suffix in product_name:
                    product_name = product_name.split(suffix)[0].strip()
                    break

            if "404" in (page.title or "") or "错误" in (page.title or ""):
                raise RuntimeError(f"页面无法访问（{page.title}），请检查链接是否正确")

            if page.ele(SCRAPER_CFG["selectors"]["v3"]["main_image"]):
                version = "v3"
            elif page.ele(SCRAPER_CFG["selectors"]["v2"]["main_image"]):
                version = "v2"
            else:
                version = "v1"
            logger.info("检测到%s页面", version.upper())

            self._download_main_images(page, task_dir, version)
            self._scroll_to_bottom(page)
            self._download_sku_images(page, task_dir, version)
            self._download_detail_images(page, task_dir, version)
        except Exception:
            logger.exception("采集过程中发生未预期错误")
            if not self.images:
                shutil.rmtree(task_dir, ignore_errors=True)
            raise
        finally:
            page.quit()

        if not self.images:
            raise RuntimeError("未采集到任何图片，页面结构可能已变更或触发反爬")

        metadata = {
            "task_id": task_id,
            "product_name": product_name,
            "product_url": product_url,
            "main_images": [i for i in self.images if i["category"] == "main"],
            "sku_images": [i for i in self.images if i["category"] == "sku"],
            "detail_images": [i for i in self.images if i["category"] == "detail"],
        }
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

    def _download_main_images(self, page, task_dir: Path, version: str) -> None:
        cfg = SCRAPER_CFG["selectors"][version]

        imgs = page.eles(cfg["main_image"])
        attrs = ("src", "data-lazyload-src") if version == "v1" else ("src",)

        logger.info("发现 %d 张主图", len(imgs))
        seen = set()
        idx = 0
        for img in imgs:
            try:
                url = None
                for attr in attrs:
                    url = img.attr(attr)
                    if url:
                        break
                if not url or url in seen:
                    continue
                seen.add(url)
                idx += 1
                filename = f"主图_{idx}.jpg"
                if self._download(url, task_dir, filename):
                    self.images.append({"filename": filename, "url": url, "category": "main"})
            except Exception:
                logger.warning("主图_%d 处理异常", idx, exc_info=True)

    def _download_sku_images(self, page, task_dir: Path, version: str) -> None:
        cfg = SCRAPER_CFG["selectors"][version]
        nodes = page.eles(cfg["sku_image"])
        logger.info("发现 %d 张 SKU 图", len(nodes))
        seen = set()
        idx = 0
        for node in nodes:
            try:
                url = node.attr("src") or self._extract_bg_url(node.attr("style"))
                if not url or url in seen:
                    continue
                seen.add(url)
                url = url.replace("_sum.jpg", "").replace("_sum.webp", "")

                label = ""
                try:
                    ancestor = node
                    for _ in range(cfg["sku_label_level"]):
                        p = ancestor.parent
                        ancestor = p() if callable(p) else p
                    label_el = ancestor.ele(cfg["sku_label"])
                    if label_el:
                        label = label_el.text.strip()
                    logger.info("SKU标签提取: level=%s selector=%s label='%s'", cfg["sku_label_level"], cfg["sku_label"], label)
                except Exception:
                    logger.warning("SKU标签提取异常", exc_info=True)

                idx += 1
                safe_label = re.sub(r'[\\/:*?"<>|]', "_", label) if label else str(idx)
                filename = f"SKU_{idx}_{safe_label}.jpg"
                if self._download(url, task_dir, filename):
                    entry = {"filename": filename, "url": url, "category": "sku"}
                    if label:
                        entry["label"] = label
                    self.images.append(entry)
            except Exception:
                logger.warning("SKU_%d 处理异常", idx, exc_info=True)

    def _download_detail_images(self, page, task_dir: Path, version: str) -> None:
        cfg = SCRAPER_CFG["selectors"][version]

        imgs = page.eles(cfg["detail_image"])
        attrs = ("src", "data-lazyload-src") if version == "v1" else ("src",)

        logger.info("发现 %d 张详情图", len(imgs))
        seen = set()
        idx = 0
        for img in imgs:
            try:
                url = None
                for attr in attrs:
                    url = img.attr(attr)
                    if url:
                        break
                if not url or url in seen:
                    continue
                seen.add(url)
                idx += 1
                filename = f"详情图_{idx}.jpg"
                if self._download(url, task_dir, filename):
                    self.images.append({"filename": filename, "url": url, "category": "detail"})
            except Exception:
                logger.warning("详情图_%d 处理异常", idx, exc_info=True)

    @staticmethod
    def _scroll_to_bottom(page) -> None:
        try:
            start = time.time()
            last_height = page.run_js("return document.body.scrollHeight;")
            while time.time() - start < SCRAPER_CFG["download"]["scroll_timeout"]:
                page.scroll.to_bottom()
                time.sleep(1)
                current = page.run_js("return document.body.scrollHeight;")
                if current == last_height:
                    break
                last_height = current
            logger.info("已滚动到页面底部")
        except Exception:
            logger.warning("滚动异常，跳过", exc_info=True)

    @staticmethod
    def _download(url: str, save_dir: Path, filename: str) -> bool:
        filename = re.sub(r'[\\/:*?"<>|]', "_", filename)
        try:
            resp = requests.get(
                url, stream=True, timeout=SCRAPER_CFG["download"]["timeout"], headers=SCRAPER_CFG["request"]["headers"],
                proxies={"http": None, "https": None},
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
        if not style:
            return None
        match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
        return match.group(1) if match else None
