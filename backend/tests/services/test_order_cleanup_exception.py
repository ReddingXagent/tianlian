"""order_cleanup_service 异常保护测试 (卡 a6e2e562)

验证 cleanup_stale_pending_orders / cancel_stale_pending_for_user 在 DB 查询/写库抛异常时:
1. 不向调用方裸抛 (被 try/except 兜底) —— 不阻塞定时任务/建单主流程
2. 调用 db.rollback() 回滚事务
3. 记录 logger.exception
4. 返回降级值 (cleanup → {"cancelled": 0}, cancel_for_user → 0)

设计: MagicMock 隔离 DB, 通过 side_effect 注入异常 (参考 test_service_db_exception_safety.py)。
"""
import logging
from unittest.mock import MagicMock

import pytest

from app.services.order_cleanup_service import (
    cleanup_stale_pending_orders,
    cancel_stale_pending_for_user,
)


# ════════════════════════════════════════════════════════════
# cleanup_stale_pending_orders
# ════════════════════════════════════════════════════════════
class TestCleanupStalePendingOrdersException:
    def test_query_failure_returns_zero_and_rolls_back(self):
        """查询 (.all) 抛异常 → 不抛出 + rollback + cancelled=0。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.side_effect = RuntimeError("db down")

        result = cleanup_stale_pending_orders(db, timeout_minutes=10)

        assert result == {"cancelled": 0}
        db.rollback.assert_called_once()

    def test_commit_failure_returns_zero_and_rolls_back(self):
        """commit 抛异常 → 不抛出 + rollback + cancelled=0。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []  # 无订单, 不触发 commit
        # 强制走 commit 路径: 返回一条超时订单
        order = MagicMock()
        order.created_at = MagicMock()
        order.created_at.tzinfo = None  # naive → _ensure_aware_utc 补 UTC
        from datetime import datetime, timedelta, timezone
        order.created_at.replace.return_value = datetime.now(timezone.utc) - timedelta(minutes=30)
        db.query.return_value.filter.return_value.all.return_value = [order]
        db.commit.side_effect = RuntimeError("db down")

        result = cleanup_stale_pending_orders(db, timeout_minutes=10)

        assert result == {"cancelled": 0}
        db.rollback.assert_called_once()

    def test_exception_logged(self, caplog):
        """异常路径记录 logger.exception。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.side_effect = RuntimeError("db down")

        with caplog.at_level(logging.ERROR, logger="app.services.order_cleanup_service"):
            cleanup_stale_pending_orders(db, timeout_minutes=10)

        assert any("pending 超时清理失败" in r.getMessage() for r in caplog.records)

    def test_exception_does_not_propagate(self):
        """异常不向调用方裸抛 (建单/定时任务不被阻塞)。"""
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")

        # 不应抛出
        result = cleanup_stale_pending_orders(db)
        assert result == {"cancelled": 0}


# ════════════════════════════════════════════════════════════
# cancel_stale_pending_for_user
# ════════════════════════════════════════════════════════════
class TestCancelStalePendingForUserException:
    def test_query_failure_returns_zero_and_rolls_back(self):
        """查询 (.all) 抛异常 → 不抛出 + rollback + 返回 0。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.side_effect = RuntimeError("db down")

        result = cancel_stale_pending_for_user(db, user_id=100, timeout_minutes=10)

        assert result == 0
        db.rollback.assert_called_once()

    def test_commit_failure_returns_zero_and_rolls_back(self):
        """commit 抛异常 → 不抛出 + rollback + 返回 0。"""
        from datetime import datetime, timedelta, timezone
        db = MagicMock()
        order = MagicMock()
        order.created_at = MagicMock()
        order.created_at.tzinfo = None
        order.created_at.replace.return_value = datetime.now(timezone.utc) - timedelta(minutes=30)
        db.query.return_value.filter.return_value.all.return_value = [order]
        db.commit.side_effect = RuntimeError("db down")

        result = cancel_stale_pending_for_user(db, user_id=100, timeout_minutes=10)

        assert result == 0
        db.rollback.assert_called_once()

    def test_exception_logged(self, caplog):
        """异常路径记录 logger.exception。"""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.side_effect = RuntimeError("db down")

        with caplog.at_level(logging.ERROR, logger="app.services.order_cleanup_service"):
            cancel_stale_pending_for_user(db, user_id=100, timeout_minutes=10)

        assert any("建单防御清理失败" in r.getMessage() for r in caplog.records)

    def test_exception_does_not_propagate(self):
        """异常不向调用方裸抛 (建单主流程不被阻塞)。"""
        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")

        assert cancel_stale_pending_for_user(db, user_id=100) == 0
