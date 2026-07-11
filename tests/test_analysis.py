"""analysis 路由层单元测试

测试策略：
- 路由处理函数 → 直接调函数 + mock deps，测返回值和 DB/Celery 调用
- Pydantic 模型 → 测字段校验
- 不测 FastAPI 框架本身（参数解析、422 响应格式等是框架的事）
"""
import pytest
from pydantic import ValidationError

from app.api.routes.analysis import submit_analysis, do_submit_strategies
from app.models import Task
from app.schemas.analysis import AnalysisSubmitRequest, StrategyRequest


# ── AnalysisSubmitRequest Pydantic 模型校验 ──

class TestAnalysisSubmitRequest:
    """测请求体模型字段校验"""

    def test_all_required_fields(self):
        body = AnalysisSubmitRequest(name="商品A", function="清洁", price="99")
        assert body.name == "商品A"
        assert body.function == "清洁"
        assert body.price == "99"
        assert body.extra == ""         # 默认值
        assert body.custom_prompt == "" # 默认值

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            AnalysisSubmitRequest(function="清洁", price="99")

    def test_missing_function_raises(self):
        with pytest.raises(ValidationError):
            AnalysisSubmitRequest(name="商品A", price="99")

    def test_missing_price_raises(self):
        with pytest.raises(ValidationError):
            AnalysisSubmitRequest(name="商品A", function="清洁")


# ── StrategyRequest Pydantic 模型校验 ──

class TestStrategyRequest:
    """测策略请求体字段校验"""

    def test_basic(self):
        body = StrategyRequest(analysis="分析文本")
        assert body.analysis == "分析文本"
        assert body.system_prompt == ""
        assert body.parent_task_id is None

    def test_missing_analysis_raises(self):
        with pytest.raises(ValidationError):
            StrategyRequest()

    def test_with_parent_task_id(self):
        body = StrategyRequest(analysis="分析文本", parent_task_id="abc12345")
        assert body.parent_task_id == "abc12345"


# ── submit_analysis 路由处理函数 ──

class TestSubmitAnalysis:
    """测 /analysis/submit 路由处理函数"""

    @pytest.mark.asyncio
    async def test_returns_task_id_and_200(self, mock_db):
        result = await submit_analysis(
            name="商品A",
            function="清洁",
            price="99",
            extra="",
            images=[],
            custom_prompt="",
            db=mock_db,
        )

        assert result["message"] == "ok"
        assert "task_id" in result["data"]
        assert result["data"]["task_type"] == "analysis"
        assert len(result["data"]["task_id"]) == 8

    @pytest.mark.asyncio
    async def test_writes_pending_task_to_db(self, mock_db):
        await submit_analysis(
            name="商品A",
            function="清洁",
            price="99",
            extra="备注",
            images=[],
            custom_prompt="请重点分析材质",
            db=mock_db,
        )

        mock_db.add.assert_called_once()
        task: Task = mock_db.add.call_args[0][0]
        assert task.type == "analysis"
        assert task.status == "PENDING"
        assert task.request_json["name"] == "商品A"
        assert task.request_json["function"] == "清洁"
        assert task.request_json["price"] == "99"
        assert task.request_json["extra"] == "备注"
        assert task.request_json["custom_prompt"] == "请重点分析材质"

    @pytest.mark.asyncio
    async def test_commits_db(self, mock_db):
        await submit_analysis(
            name="商品A",
            function="清洁",
            price="99",
            extra="",
            images=[],
            custom_prompt="",
            db=mock_db,
        )

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_celery_task(self, mock_db):
        from unittest.mock import patch as mock_patch

        with mock_patch("app.api.routes.analysis.analyze_product_task") as mock_task:
            result = await submit_analysis(
                name="商品A",
                function="清洁",
                price="99",
                extra="",
                images=[],
                custom_prompt="",
                db=mock_db,
            )

            mock_task.delay.assert_called_once_with(task_id=result["data"]["task_id"])


# ── do_submit_strategies 路由处理函数 ──

class TestDoSubmitStrategies:
    """测 /analysis/strategies 路由处理函数"""

    @pytest.mark.asyncio
    async def test_returns_task_id_and_200(self, mock_db):
        body = StrategyRequest(analysis="分析文本内容")
        result = await do_submit_strategies(body=body, db=mock_db)

        assert result["message"] == "ok"
        assert "task_id" in result["data"]
        assert result["data"]["task_type"] == "strategy"
        assert len(result["data"]["task_id"]) == 8

    @pytest.mark.asyncio
    async def test_writes_pending_task_with_correct_type(self, mock_db):
        body = StrategyRequest(analysis="分析文本ABC", system_prompt="你是专家")
        await do_submit_strategies(body=body, db=mock_db)

        mock_db.add.assert_called_once()
        task: Task = mock_db.add.call_args[0][0]
        assert task.type == "strategy"
        assert task.status == "PENDING"
        assert task.request_json["analysis"] == "分析文本ABC"
        assert task.request_json["system_prompt"] == "你是专家"
        assert task.parent_task_id is None

    @pytest.mark.asyncio
    async def test_stores_parent_task_id(self, mock_db):
        body = StrategyRequest(analysis="分析文本", parent_task_id="abc12345")
        await do_submit_strategies(body=body, db=mock_db)

        task: Task = mock_db.add.call_args[0][0]
        assert task.parent_task_id == "abc12345"

    @pytest.mark.asyncio
    async def test_dispatches_celery_strategy_task(self, mock_db):
        from unittest.mock import patch as mock_patch

        with mock_patch("app.api.routes.analysis.strategy_task") as mock_task:
            body = StrategyRequest(analysis="分析文本")
            await do_submit_strategies(body=body, db=mock_db)

            mock_task.delay.assert_called_once()
