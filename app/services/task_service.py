"""任务服务 — 统一管理 Task 的创建与 Celery 派发。"""
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task
from app.models.task import gen_task_id
from app.repositories.task_repo import AsyncTaskRepo


class TaskService:
    """路由层通过此类创建任务，不再直接操作 Task 模型。"""

    @staticmethod
    async def create_and_dispatch(
        db: AsyncSession,
        *,
        type: str,
        request_json: dict[str, Any],
        celery_task: Any,
        parent_task_id: Optional[str] = None,
    ) -> Task:
        """创建任务并派发 Celery。

        Args:
            db: 异步数据库会话
            type: 任务类型（scrape / analysis / image_gen / ...）
            request_json: 前端传来的请求参数，存入 Task.request_json
            celery_task: Celery 任务装饰器对象，例如 `scrape_product_task`
            parent_task_id: 可选，父任务 ID（策略任务链接分析任务）

        Returns:
            已持久化的 Task 对象，路由可直接取 .task_id 返回前端
        """
        task = await AsyncTaskRepo.create_pending(
            db,
            task_id=gen_task_id(),
            type=type,
            request_json=request_json,
            parent_task_id=parent_task_id,
        )
        celery_task.delay(task_id=task.task_id)
        return task
