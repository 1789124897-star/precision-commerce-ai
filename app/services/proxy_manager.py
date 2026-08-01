"""代理管理器 —— 免费代理轮换池 + BrightData 付费代理。"""
import logging
import random
import uuid

import requests

FREE_API = "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text"
VPN = "http://127.0.0.1:33210"

logger = logging.getLogger(__name__)


class ProxyManager:
    """代理管理器 —— .env 里 PROXY_PROVIDER 控制 none/free/brightdata 三种模式。"""

    def __init__(self, provider, host, port, username, password):
        self.provider = (provider or "none").strip().lower()
        self.host = host
        self.port = port
        self.username = username
        self.password = password

        self.proxy_list = []
        self.pointer = 0
        self.blacklist = set()

    def get_next(self):
        """取一个代理。直连返回空，付费返回 BrightData URL，免费走轮换池。"""
        if self.provider == "none":
            return ""
        if self.provider == "brightdata":
            sid = uuid.uuid4().hex[:8]
            return f"http://{self.username}-session-{sid}:{self.password}@{self.host}:{self.port}"
        return self._free_next()

    def mark_failed(self, proxy):
        """标记代理已失效。"""
        self.blacklist.add(proxy)

    def _free_next(self):
        """免费模式：从池子里取下一个可用代理，全挂了则重新拉取。"""
        if len(self.proxy_list) == 0:
            self._pull_list()
        if len(self.proxy_list) == 0:
            return ""

        total = len(self.proxy_list)
        tried = 0
        while tried < total:
            p = self.proxy_list[self.pointer]
            self.pointer = self.pointer + 1
            if self.pointer >= total:
                self.pointer = 0
            tried = tried + 1
            if p not in self.blacklist:
                return p

        logger.warning("免费代理全挂了，重新拉取...")
        self._pull_list()
        if len(self.proxy_list) == 0:
            return ""
        p = self.proxy_list[0]
        self.pointer = 1
        return p

    def _pull_list(self):
        """从 proxyscrape API 拉免费代理列表。"""
        try:
            resp = requests.get(FREE_API, proxies={"http": VPN, "https": VPN}, timeout=15)
            lines = resp.text.strip().splitlines()
            new_list = []
            for line in lines:
                if line.startswith("http://") or line.startswith("https://"):
                    new_list.append(line)
            random.shuffle(new_list)
            self.proxy_list = new_list
            self.pointer = 0
            self.blacklist.clear()
            logger.info("拉到 %d 个免费代理", len(self.proxy_list))
        except Exception as e:
            logger.warning("拉免费代理失败: %s", e)
            self.proxy_list = []
