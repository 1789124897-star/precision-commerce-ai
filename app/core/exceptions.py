"""业务异常 — 抛出时指定 HTTP 状态码，全局 handler 自动转 JSON 响应。"""


class AppException(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
