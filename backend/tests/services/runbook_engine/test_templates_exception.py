"""test_templates_exception.py — RunbookTemplate 入口异常保护测试

被测卡片: d23b9a2d
同卡: storage_optimizer.py (见 tests/services/charging/test_storage_optimizer_exception.py)

设计: match()/get_default() 为纯字典查找入口(无 DB 查询/写入), 故通过
monkeypatch 注入运行时异常, 验证顶层 try/except 健壮性兜底:
1. match() 内部异常 → 返回 None(让 engine.py 回退 get_default, 见 engine.py:138-143
   ``if not template: template = RunbookTemplate.get_default()``), 不裸抛,
   记录 logger.exception
2. get_default() 内部异常 → 返回最小通用模板(必须含 ``steps`` key, engine 后续
   ``template["steps"]`` 解引用), 不裸抛
3. 正常输入 → 结果与未加保护时完全一致(回归保护)
"""
import logging

from app.services.runbook_engine.templates import RunbookTemplate

LOGGER_NAME = "app.services.runbook_engine.templates"


class _ExplodingMapping:
    """访问即抛, 模拟 TEMPLATES 数据源不可用。"""

    def __contains__(self, key):
        raise RuntimeError("模板数据源不可用(模拟)")

    def __getitem__(self, key):
        raise RuntimeError("模板数据源不可用(模拟)")

    def items(self):
        raise RuntimeError("模板数据源不可用(模拟)")

    def get(self, key, default=None):
        raise RuntimeError("模板数据源不可用(模拟)")


# ─── 1. match() 内部异常 → None ───

class TestMatchExceptionSafety:
    def test_internal_exception_returns_none(self, monkeypatch):
        """engine 契约: match 返回 None → 回退 get_default"""
        monkeypatch.setattr(RunbookTemplate, "TEMPLATES", _ExplodingMapping())

        result = RunbookTemplate.match("逆变器通讯中断")

        assert result is None

    def test_internal_exception_does_not_propagate(self, monkeypatch):
        monkeypatch.setattr(RunbookTemplate, "TEMPLATES", _ExplodingMapping())
        # 不应裸抛(engine 在请求路径中同步调用 match)
        RunbookTemplate.match("任意故障", device_type="inverter")

    def test_internal_exception_logs_error(self, monkeypatch, caplog):
        monkeypatch.setattr(RunbookTemplate, "TEMPLATES", _ExplodingMapping())

        with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
            RunbookTemplate.match("故障X")

        assert any(r.levelno == logging.ERROR and r.exc_info for r in caplog.records)


# ─── 2. get_default() 内部异常 → 最小通用模板(含 steps) ───

class TestGetDefaultExceptionSafety:
    @staticmethod
    def _patch_step_to_raise(monkeypatch):
        """让 RunbookStep 构造抛, 模拟模型构造失败。"""
        def _boom(*args, **kwargs):
            raise RuntimeError("模型构造失败(模拟)")
        monkeypatch.setattr(
            "app.services.runbook_engine.templates.RunbookStep", _boom
        )

    def test_internal_exception_returns_minimal_template(self, monkeypatch):
        self._patch_step_to_raise(monkeypatch)

        result = RunbookTemplate.get_default()

        # engine 后续必访问 template["steps"]
        assert isinstance(result, dict)
        assert "steps" in result

    def test_internal_exception_does_not_propagate(self, monkeypatch):
        self._patch_step_to_raise(monkeypatch)
        RunbookTemplate.get_default()  # 不应裸抛

    def test_internal_exception_logs_error(self, monkeypatch, caplog):
        self._patch_step_to_raise(monkeypatch)

        with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
            RunbookTemplate.get_default()

        assert any(r.levelno == logging.ERROR and r.exc_info for r in caplog.records)


# ─── 3. 正常流程结果不变(回归保护) ───

class TestNormalFlowUnchanged:
    def test_exact_match(self):
        r = RunbookTemplate.match("逆变器通讯中断")
        assert r is not None
        assert r["category"] == "inverter"

    def test_no_match_returns_none(self):
        """无任何匹配 → None(引擎回退 get_default)"""
        assert RunbookTemplate.match("zzz不存在的故障xyz") is None

    def test_get_default_structure(self):
        r = RunbookTemplate.get_default()
        assert r["category"] == "general"
        assert "steps" in r
        assert len(r["steps"]) >= 1

    def test_device_type_fallback(self):
        """device_type 兜底匹配"""
        r = RunbookTemplate.match("未知故障", device_type="charger")
        assert r is not None
        assert r["category"] == "charger"
