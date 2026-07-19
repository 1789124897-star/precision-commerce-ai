"""日志配置 —— 四层分离：app.log / error.log / task.log + 控制台
排错优先级：error.log → task.log → app.log
"""
import logging
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FMT = "%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s"


class _LoggerFilter(logging.Filter):
    """只放行 logger 名以指定前缀开头的记录"""
    def __init__(self, prefixes: tuple[str, ...]):
        super().__init__()
        self._prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith(self._prefixes)


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    fmt = logging.Formatter(LOG_FMT, datefmt="%m-%d %H:%M:%S")

    # 1. 控制台：全部 INFO+，开发直观
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    # 2. app.log：主日志，所有模块 INFO+
    app_fh = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
    app_fh.setLevel(logging.INFO)
    app_fh.setFormatter(fmt)

    # 3. error.log：只记 ERROR+，出问题第一眼看这
    err_fh = logging.FileHandler(LOG_DIR / "error.log", encoding="utf-8")
    err_fh.setLevel(logging.ERROR)
    err_fh.setFormatter(fmt)

    # 4. task.log：Celery + 自定义任务轨迹
    task_fh = logging.FileHandler(LOG_DIR / "task.log", encoding="utf-8")
    task_fh.setLevel(logging.INFO)
    task_fh.setFormatter(fmt)
    task_fh.addFilter(_LoggerFilter(("app.tasks", "celery")))

    root.addHandler(console)
    root.addHandler(app_fh)
    root.addHandler(err_fh)
    root.addHandler(task_fh)

    # 静默 SQLAlchemy 引擎 SQL
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
