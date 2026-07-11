"""pytest 全局 fixtures"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _mock_celery():
    """全局 mock：防止任何测试意外触发真实 Celery 连接"""
    mock = MagicMock()
    mock.task.return_value = lambda f: f
    with (
        patch("celery.Celery", return_value=mock),
        patch("app.api.routes.analysis.analyze_product_task.delay"),
        patch("app.tasks.analysis.analyze_product_task.delay"),
        patch("app.api.routes.analysis.strategy_task.delay"),
        patch("app.tasks.strategy.strategy_task.delay"),
        patch("app.api.routes.analysis.save_upload", return_value="/output/uploads/test.png"),
    ):
        yield


@pytest.fixture
def mock_db():
    """模拟数据库 AsyncSession

    AsyncMock 默认所有方法返回协程，但 db.add() 是同步方法，
    需要单独设为 MagicMock 避免 'coroutine was never awaited' 警告。
    """
    session = AsyncMock()
    session.add = MagicMock()  # 同步方法
    return session
