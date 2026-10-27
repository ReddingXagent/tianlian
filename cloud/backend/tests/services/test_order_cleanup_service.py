"""pending 订单超时清理服务测试 (卡 6ff02fd2)

被测: app.services.order_cleanup_service.cleanup_stale_pending_orders
设计: test_db fixture 走真实 SQLite, 直接构造 ChargingOrder 行, 断言状态流转 + 返回统计。
覆盖边界: 超时/未超时/临界点/非pending/批量/自定义timeout/naive created_at 兼容。
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
)
from app.services.order_cleanup_service import cleanup_stale_pending_orders


def _make_order(db, *, order_no, status, created_at, device_id=1, user_id=100):
    """构造一行 ChargingOrder; created_at 可为 aware/naive datetime。"""
    order = ChargingOrder(
        order_no=order_no,
        station_id=1,
        device_id=device_id,
        connector_id=1,
        user_id=user_id,
        user_type=None,
        payment_status=OrderPaymentStatus.UNPAID,
        order_status=status,
        created_at=created_at,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


# ═══════════════════════════════════════════════════════════════
# 基础清理逻辑
# ═══════════════════════════════════════════════════════════════
class TestCleanupStalePendingOrders:
    """cleanup_stale_pending_orders 状态流转 + 统计"""

    def test_cancels_order_past_timeout(self, test_db):
        """pending 超过 timeout 的订单 → cancelled, 返回 cancelled=1。"""
        db = test_db["session"]
        old = datetime.now(timezone.utc) - timedelta(minutes=15)
        _make_order(db, order_no="TL_OLD1", status=OrderStatus.PENDING, created_at=old)

        result = cleanup_stale_pending_orders(db, timeout_minutes=10)

        assert result["cancelled"] == 1
        db.expire_all()
        order = db.query(ChargingOrder).filter_by(order_no="TL_OLD1").one()
        assert order.order_status == OrderStatus.CANCELLED
        assert order.end_time is not None
        assert order.stop_reason == "pending_timeout"

    def test_keeps_fresh_pending_order(self, test_db):
        """pending 未超 timeout 的订单保持 pending, cancelled=0。"""
        db = test_db["session"]
        recent = datetime.now(timezone.utc) - timedelta(minutes=3)
        _make_order(db, order_no="TL_FRESH", status=OrderStatus.PENDING, created_at=recent)

        result = cleanup_stale_pending_orders(db, timeout_minutes=10)

        assert result["cancelled"] == 0
        db.expire_all()
        order = db.query(ChargingOrder).filter_by(order_no="TL_FRESH").one()
        assert order.order_status == OrderStatus.PENDING

    def test_boundary_just_under_timeout_not_cancelled(self, test_db):
        """created_at 略晚于 now-timeout (差 30s) 视为未超时, cancelled=0。

        注: 严格边界 created_at == cutoff 在时间流动下不稳定 (执行 cleanup 时已过数毫秒),
        故用 -9.5min 锚定 "未超时" 侧。
        """
        db = test_db["session"]
        just_under = datetime.now(timezone.utc) - timedelta(minutes=9, seconds=30)
        _make_order(db, order_no="TL_BOUND", status=OrderStatus.PENDING, created_at=just_under)

        result = cleanup_stale_pending_orders(db, timeout_minutes=10)

        assert result["cancelled"] == 0

    def test_ignores_non_pending_statuses(self, test_db):
        """charging/completed/cancelled/failed 订单不被清理, 即使很旧。"""
        db = test_db["session"]
        old = datetime.now(timezone.utc) - timedelta(minutes=60)
        for i, st in enumerate([
            OrderStatus.CHARGING,
            OrderStatus.COMPLETED,
            OrderStatus.CANCELLED,
            OrderStatus.FAILED,
        ]):
            _make_order(db, order_no=f"TL_ST{i}", status=st, created_at=old, device_id=10 + i)

        result = cleanup_stale_pending_orders(db, timeout_minutes=10)

        assert result["cancelled"] == 0

    def test_batch_cancel_multiple(self, test_db):
        """多笔超时 pending 一次性清理, cancelled 计数正确。"""
        db = test_db["session"]
        old = datetime.now(timezone.utc) - timedelta(minutes=30)
        for i in range(3):
            _make_order(db, order_no=f"TL_BATCH{i}", status=OrderStatus.PENDING, created_at=old, device_id=20 + i)

        result = cleanup_stale_pending_orders(db, timeout_minutes=10)

        assert result["cancelled"] == 3
        db.expire_all()
        cancelled = (
            db.query(ChargingOrder)
            .filter(ChargingOrder.order_no.like("TL_BATCH%"))
            .all()
        )
        assert all(o.order_status == OrderStatus.CANCELLED for o in cancelled)

    def test_custom_timeout_minutes(self, test_db):
        """timeout_minutes=1 → 2 分钟前的订单被清理。"""
        db = test_db["session"]
        created = datetime.now(timezone.utc) - timedelta(minutes=2)
        _make_order(db, order_no="TL_T1", status=OrderStatus.PENDING, created_at=created)

        result = cleanup_stale_pending_orders(db, timeout_minutes=1)

        assert result["cancelled"] == 1

    def test_naive_created_at_treated_as_utc(self, test_db):
        """SQLite 读回的 created_at 为 naive (无 tzinfo), 须按 UTC 处理不报错。"""
        db = test_db["session"]
        order = _make_order(
            db,
            order_no="TL_NAIVE",
            status=OrderStatus.PENDING,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        )
        # 模拟 SQLite 读回的 naive 场景: 直接抹掉 tzinfo 后写库再清
        order.created_at = order.created_at.replace(tzinfo=None)
        db.commit()

        result = cleanup_stale_pending_orders(db, timeout_minutes=10)

        assert result["cancelled"] == 1

    def test_default_timeout_is_ten_minutes(self, test_db):
        """不传 timeout_minutes 时默认 10 分钟: 9min 不清, 11min 清。"""
        db = test_db["session"]
        _make_order(
            db,
            order_no="TL_D9",
            status=OrderStatus.PENDING,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=9),
            device_id=30,
        )
        _make_order(
            db,
            order_no="TL_D11",
            status=OrderStatus.PENDING,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=11),
            device_id=31,
        )

        result = cleanup_stale_pending_orders(db)

        assert result["cancelled"] == 1
        db.expire_all()
        assert db.query(ChargingOrder).filter_by(order_no="TL_D9").one().order_status == OrderStatus.PENDING
        assert db.query(ChargingOrder).filter_by(order_no="TL_D11").one().order_status == OrderStatus.CANCELLED
