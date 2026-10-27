"""AuditService 单元测试 — 审计日志记录/查询/统计

纯逻辑测试, DB 用 MagicMock 隔离, 不连真实数据库。覆盖:
- _get_db / _close_db 的 owned 语义 (外部传入 db 不关闭, 自建 db 关闭)
- log: 正常写入 / 异常回滚 / owned 关闭行为
- get_logs: 多维过滤 (action/module/username ilike/result/hours) + 分页 + 返回结构
- get_stats: 统计聚合 (total/today/failed/by_action/by_module)
- log_login / log_crud: 字段映射
"""
import logging
from unittest.mock import MagicMock, patch

import pytest

from app.models.audit_log import AuditLog
from app.services.audit_service import AuditService, audit_service


# ─── 辅助: 构造一个 filter/order_by/offset/limit 全部自返回的 query mock ───

def _chain_query_mock(count=0, items=None):
    """返回 (db, q): db.query() 永远返回 q, q 上的链式方法都返回 q 自身。"""
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.count.return_value = count
    q.all.return_value = items if items is not None else []
    return db, q


# ═══════════════════════════════════════════
# _get_db / _close_db 语义
# ═══════════════════════════════════════════

class TestDbOwnership:
    def test_get_db_returns_passed_session(self):
        svc = AuditService()
        external = MagicMock()
        assert svc._get_db(external) is external

    def test_get_db_creates_sessionlocal_when_none(self):
        svc = AuditService()
        with patch("app.core.database.SessionLocal") as sl:
            fake = MagicMock()
            sl.return_value = fake
            assert svc._get_db(None) is fake
            sl.assert_called_once_with()

    def test_close_db_closes_when_owned(self):
        svc = AuditService()
        s = MagicMock()
        svc._close_db(s, owned=True)
        s.close.assert_called_once_with()

    def test_close_db_does_not_close_when_not_owned(self):
        svc = AuditService()
        s = MagicMock()
        svc._close_db(s, owned=False)
        s.close.assert_not_called()


# ═══════════════════════════════════════════
# log
# ═══════════════════════════════════════════

class TestLog:
    def test_log_with_external_db_commits_and_does_not_close(self):
        svc = AuditService()
        db = MagicMock()
        entry = svc.log(db=db, action="login", module="auth", username="u1")
        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once()
        # 外部传入的 db 不应被关闭
        db.close.assert_not_called()
        assert isinstance(entry, AuditLog)
        assert entry.action == "login"

    def test_log_without_db_owns_and_closes_session(self):
        svc = AuditService()
        fake_session = MagicMock()
        with patch("app.core.database.SessionLocal", return_value=fake_session):
            entry = svc.log(action="create", module="users", username="u2")
        fake_session.commit.assert_called_once()
        fake_session.close.assert_called_once()
        assert isinstance(entry, AuditLog)

    def test_log_exception_rolls_back_and_returns_none(self):
        svc = AuditService()
        db = MagicMock()
        db.commit.side_effect = RuntimeError("boom")
        result = svc.log(db=db, action="delete", module="users")
        db.rollback.assert_called_once()
        assert result is None
        # 异常路径仍走 finally, 但外部 db 不关闭
        db.close.assert_not_called()

    def test_log_exception_owned_session_still_closed(self):
        svc = AuditService()
        fake_session = MagicMock()
        fake_session.commit.side_effect = RuntimeError("boom")
        with patch("app.core.database.SessionLocal", return_value=fake_session):
            result = svc.log(action="x")
        fake_session.rollback.assert_called_once()
        fake_session.close.assert_called_once()
        assert result is None


# ═══════════════════════════════════════════
# get_logs
# ═══════════════════════════════════════════

class TestGetLogs:
    def test_get_logs_default_structure(self):
        svc = AuditService()
        db, q = _chain_query_mock(count=0, items=[])
        res = svc.get_logs(db=db)
        assert res == {"items": [], "total": 0, "page": 1, "page_size": 20}
        # 无任何过滤条件时不调用 filter
        q.filter.assert_not_called()

    def test_get_logs_applies_each_filter(self):
        svc = AuditService()
        item = AuditLog(action="login", module="auth", username="u")
        db, q = _chain_query_mock(count=1, items=[item])
        svc.get_logs(
            db=db,
            action="login",
            module="auth",
            username="adm",
            result="success",
            hours=24,
            page=2,
            page_size=10,
        )
        # 5 个过滤条件各调用一次 filter
        assert q.filter.call_count == 5
        # offset = (page-1) * page_size = 10
        q.offset.assert_called_once_with(10)
        q.limit.assert_called_once_with(10)

    def test_get_logs_pagination_offset(self):
        svc = AuditService()
        db, q = _chain_query_mock(count=100, items=[])
        svc.get_logs(page=3, page_size=15, db=db)
        q.offset.assert_called_once_with(30)
        q.limit.assert_called_once_with(15)

    def test_get_logs_serializes_items_via_to_dict(self):
        svc = AuditService()
        a = AuditLog(action="login", module="auth", username="u1")
        a.id = 7
        b = AuditLog(action="export", module="reports", username="u2")
        b.id = 8
        db, q = _chain_query_mock(count=2, items=[a, b])
        res = svc.get_logs(db=db)
        assert res["total"] == 2
        assert [it["id"] for it in res["items"]] == [7, 8]
        assert res["items"][0]["action"] == "login"

    def test_get_logs_without_db_closes_owned_session(self):
        svc = AuditService()
        fake_session = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.offset.return_value = q
        q.limit.return_value = q
        q.count.return_value = 0
        q.all.return_value = []
        fake_session.query.return_value = q
        with patch("app.core.database.SessionLocal", return_value=fake_session):
            svc.get_logs()
        fake_session.close.assert_called_once()


# ═══════════════════════════════════════════
# get_stats
# ═══════════════════════════════════════════

class TestGetStats:
    def test_get_stats_aggregates_each_query(self):
        svc = AuditService()
        db = MagicMock()
        m_total = MagicMock(); m_total.count.return_value = 100
        m_today = MagicMock(); m_today.filter.return_value.count.return_value = 7
        m_action = MagicMock()
        m_action.group_by.return_value.all.return_value = [("login", 60), ("create", 40)]
        m_module = MagicMock()
        m_module.group_by.return_value.all.return_value = [("auth", 55), ("users", 45)]
        m_failed = MagicMock(); m_failed.filter.return_value.count.return_value = 3
        # get_stats 内部连续 5 次 db.query()
        db.query.side_effect = [m_total, m_today, m_action, m_module, m_failed]

        stats = svc.get_stats(db=db)
        assert stats["total_logs"] == 100
        assert stats["today_logs"] == 7
        assert stats["failed_logs"] == 3
        assert stats["by_action"] == {"login": 60, "create": 40}
        assert stats["by_module"] == {"auth": 55, "users": 45}

    def test_get_stats_empty_dict_when_no_rows(self):
        svc = AuditService()
        db = MagicMock()
        m = MagicMock()
        m.count.return_value = 0
        m.filter.return_value.count.return_value = 0
        m.group_by.return_value.all.return_value = []
        db.query.return_value = m
        stats = svc.get_stats(db=db)
        assert stats["total_logs"] == 0
        assert stats["today_logs"] == 0
        assert stats["failed_logs"] == 0
        assert stats["by_action"] == {}
        assert stats["by_module"] == {}


# ═══════════════════════════════════════════
# log_login / log_crud
# ═══════════════════════════════════════════

class TestLogHelpers:
    def test_log_login_success_maps_fields(self):
        svc = AuditService()
        db = MagicMock()
        entry = svc.log_login(user_id=1, username="alice", ip="1.2.3.4", success=True, db=db)
        assert entry.action == "login"
        assert entry.module == "auth"
        assert entry.result == "success"
        assert entry.ip_address == "1.2.3.4"
        assert entry.username == "alice"
        assert entry.error_msg is None

    def test_log_login_failure_maps_result_and_error(self):
        svc = AuditService()
        db = MagicMock()
        entry = svc.log_login(user_id=2, username="bob", success=False, error="bad password", db=db)
        assert entry.result == "failure"
        assert entry.error_msg == "bad password"

    def test_log_crud_forwards_all_fields(self):
        svc = AuditService()
        db = MagicMock()
        entry = svc.log_crud(
            user_id=3, username="carol", action="update", module="devices",
            target_id="D-1", target_desc="逆变器#1", detail="改额定功率",
            old_value="100", new_value="120", ip="10.0.0.1", db=db,
        )
        assert entry.action == "update"
        assert entry.module == "devices"
        assert entry.target_id == "D-1"
        assert entry.target_desc == "逆变器#1"
        assert entry.old_value == "100"
        assert entry.new_value == "120"
        assert entry.ip_address == "10.0.0.1"

    def test_module_singleton_is_instance(self):
        assert isinstance(audit_service, AuditService)


# ═══════════════════════════════════════════
# 输入校验: page / page_size 越界自动修正
# ═══════════════════════════════════════════

class TestGetLogsPaginationClamp:
    def test_page_below_one_clamped_to_one(self):
        svc = AuditService()
        db, q = _chain_query_mock(count=0, items=[])
        res = svc.get_logs(page=0, page_size=10, db=db)
        assert res["page"] == 1
        q.offset.assert_called_once_with(0)  # (1-1)*10

    def test_page_negative_clamped_to_one(self):
        svc = AuditService()
        db, q = _chain_query_mock(count=0, items=[])
        res = svc.get_logs(page=-5, db=db)
        assert res["page"] == 1

    def test_page_size_above_max_clamped_to_hundred(self):
        svc = AuditService()
        db, q = _chain_query_mock(count=0, items=[])
        res = svc.get_logs(page_size=200, db=db)
        assert res["page_size"] == 100
        q.limit.assert_called_once_with(100)

    def test_page_size_below_one_clamped_to_one(self):
        svc = AuditService()
        db, q = _chain_query_mock(count=0, items=[])
        res = svc.get_logs(page_size=0, db=db)
        assert res["page_size"] == 1
        q.limit.assert_called_once_with(1)

    def test_normal_pagination_not_clamped(self):
        # 回归: 合法参数不被误修正
        svc = AuditService()
        db, q = _chain_query_mock(count=0, items=[])
        res = svc.get_logs(page=3, page_size=50, db=db)
        assert res["page"] == 3
        assert res["page_size"] == 50
        q.offset.assert_called_once_with(100)  # (3-1)*50
        q.limit.assert_called_once_with(50)


# ═══════════════════════════════════════════
# 异常路径: rollback + 记日志 + 返回空结果
# ═══════════════════════════════════════════

class TestExceptionSafety:
    def test_get_logs_exception_returns_empty_dict_and_rolls_back(self):
        svc = AuditService()
        db = MagicMock()
        db.query.side_effect = RuntimeError("db explode")
        res = svc.get_logs(db=db)
        assert res == {"items": [], "total": 0, "page": 1, "page_size": 20}
        db.rollback.assert_called_once()
        # 外部传入的 db 不关闭
        db.close.assert_not_called()

    def test_get_logs_exception_owned_session_rolled_back_and_closed(self):
        svc = AuditService()
        fake_session = MagicMock()
        fake_session.query.side_effect = RuntimeError("boom")
        with patch("app.core.database.SessionLocal", return_value=fake_session):
            res = svc.get_logs()
        assert res == {"items": [], "total": 0, "page": 1, "page_size": 20}
        fake_session.rollback.assert_called_once()
        fake_session.close.assert_called_once()

    def test_get_logs_exception_logs_error(self, caplog):
        svc = AuditService()
        db = MagicMock()
        db.query.side_effect = RuntimeError("db explode")
        with caplog.at_level(logging.ERROR, logger="app.services.audit_service"):
            svc.get_logs(db=db)
        assert any("审计日志查询失败" in r.message for r in caplog.records)

    def test_get_stats_exception_returns_empty_dict_and_rolls_back(self):
        svc = AuditService()
        db = MagicMock()
        db.query.side_effect = RuntimeError("db explode")
        stats = svc.get_stats(db=db)
        assert stats == {
            "total_logs": 0,
            "today_logs": 0,
            "failed_logs": 0,
            "by_action": {},
            "by_module": {},
        }
        db.rollback.assert_called_once()
        db.close.assert_not_called()

    def test_get_stats_exception_logs_error(self, caplog):
        svc = AuditService()
        db = MagicMock()
        db.query.side_effect = RuntimeError("db explode")
        with caplog.at_level(logging.ERROR, logger="app.services.audit_service"):
            svc.get_stats(db=db)
        assert any("审计日志统计失败" in r.message for r in caplog.records)


# ═══════════════════════════════════════════
# log_crud 非空校验
# ═══════════════════════════════════════════

class TestLogCrudValidation:
    def test_log_crud_returns_none_when_action_empty_string(self):
        svc = AuditService()
        db = MagicMock()
        result = svc.log_crud(user_id=1, username="u", action="", module="users", db=db)
        assert result is None
        db.add.assert_not_called()

    def test_log_crud_returns_none_when_action_none(self):
        svc = AuditService()
        db = MagicMock()
        result = svc.log_crud(user_id=1, username="u", action=None, module="users", db=db)
        assert result is None
        db.add.assert_not_called()

    def test_log_crud_returns_none_when_module_empty_string(self):
        svc = AuditService()
        db = MagicMock()
        result = svc.log_crud(user_id=1, username="u", action="create", module="", db=db)
        assert result is None
        db.add.assert_not_called()

    def test_log_crud_returns_none_when_module_none(self):
        svc = AuditService()
        db = MagicMock()
        result = svc.log_crud(user_id=1, username="u", action="create", module=None, db=db)
        assert result is None
        db.add.assert_not_called()

    def test_log_crud_valid_args_not_blocked(self):
        # 回归: 合法参数不被误拦
        svc = AuditService()
        db = MagicMock()
        entry = svc.log_crud(
            user_id=1, username="u", action="create", module="users", db=db,
        )
        assert isinstance(entry, AuditLog)
        assert entry.action == "create"
        db.add.assert_called_once()
