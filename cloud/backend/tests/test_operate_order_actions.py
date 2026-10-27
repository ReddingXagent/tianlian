"""
异常订单操作闭环 (卡 f730f63c)

覆盖新增写端点:
- POST /api/v1/operate/orders/{id}/resolve     标记处理 (handle_type + remark, 幂等)
- POST /api/v1/operate/orders/{id}/retry-charge 重试计费 (仅 failed, 幂等)

team_scope: 复用公共 helper assert_order_team_access (与退款端点 order_fees.py 同源,
退款安全测试 test_refund_safety.py 亦以直接函数调用方式覆盖, 此处沿用同一惯例)。
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

# 先经 order_fees 入口触发 app.api.v1 完整加载, 规避 deps ↔ api.v1.__init__ 循环 import
# (与 test_refund_safety.py 同样的 import 惯例)。
from app.api.v1.order_fees import router as _order_fees_router  # noqa: F401
from app.api.deps import assert_order_team_access
from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, UserType,
)
from app.models.order_fee_item import OrderFeeItem
from app.models.station import Station
from app.models.user import User, UserRole


# ─── 种子数据 ───

def _seed_station(session, station_id=1, team_id=None):
    session.add(Station(
        id=station_id, name=f"测试站{station_id}", code=f"ST{station_id}", team_id=team_id,
    ))
    session.commit()


def _seed_order(session, order_no="AB-001", station_id=1, status=OrderStatus.FAILED,
                charged_kwh=Decimal("10"), paid_amount=Decimal("0"),
                payment_status=OrderPaymentStatus.UNPAID):
    order = ChargingOrder(
        order_no=order_no, station_id=station_id, device_id=1, user_id=101,
        user_type=UserType.APP, plate_number="京A00001",
        charged_kwh=charged_kwh, total_amount=Decimal("0"), paid_amount=paid_amount,
        order_status=status, payment_status=payment_status,
        start_time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


# ════════════════════════════════════════════════════════════
# resolve: 标记处理
# ════════════════════════════════════════════════════════════
class TestResolveAbnormalOrder:
    def test_resolve_marks_order(self, client):
        """标记处理 → 落库 handle_type/remark/handled_at/handled_by。"""
        order = _seed_order(client._sesh)
        r = client.post(
            f"/api/v1/operate/orders/{order.id}/resolve",
            json={"handle_type": "written_off", "remark": "设备故障无法恢复"},
        )
        assert r.status_code == 200
        client._sesh.refresh(order)
        assert order.abnormal_handle_type == "written_off"
        assert order.abnormal_handle_remark == "设备故障无法恢复"
        assert order.abnormal_handled_at is not None
        assert order.abnormal_handled_by is not None

    def test_resolve_idempotent_overwrite(self, client):
        """重复 resolve → 覆盖更新(幂等), 第二次值生效, 不报错。"""
        order = _seed_order(client._sesh, order_no="AB-IDEMP")
        r1 = client.post(
            f"/api/v1/operate/orders/{order.id}/resolve",
            json={"handle_type": "false_alarm"},
        )
        assert r1.status_code == 200
        r2 = client.post(
            f"/api/v1/operate/orders/{order.id}/resolve",
            json={"handle_type": "refunded", "remark": "改判为退款"},
        )
        assert r2.status_code == 200
        client._sesh.refresh(order)
        # 第二次覆盖第一次
        assert order.abnormal_handle_type == "refunded"
        assert order.abnormal_handle_remark == "改判为退款"

    def test_resolve_invalid_handle_type_rejected(self, client):
        """非法 handle_type → 422 (Literal 校验)。"""
        order = _seed_order(client._sesh, order_no="AB-INVAL")
        r = client.post(
            f"/api/v1/operate/orders/{order.id}/resolve",
            json={"handle_type": "bogus_type"},
        )
        assert r.status_code == 422

    def test_resolve_requires_handle_type(self, client):
        """缺 handle_type → 422。"""
        order = _seed_order(client._sesh, order_no="AB-MISS")
        r = client.post(
            f"/api/v1/operate/orders/{order.id}/resolve",
            json={"remark": "缺类型"},
        )
        assert r.status_code == 422

    def test_resolve_not_found(self, client):
        """不存在订单 → 404。"""
        r = client.post(
            "/api/v1/operate/orders/999999/resolve",
            json={"handle_type": "written_off"},
        )
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════
# retry-charge: 重试计费
# ════════════════════════════════════════════════════════════
class TestRetryCharge:
    def test_retry_charge_failed_order_generates_bill(self, client):
        """failed 订单重试计费 → 生成 fee_items + total_amount>0 (默认费率兜底)。"""
        _seed_station(client._sesh, station_id=1)
        order = _seed_order(client._sesh, order_no="AB-RTRY", charged_kwh=Decimal("10"))
        r = client.post(f"/api/v1/operate/orders/{order.id}/retry-charge")
        assert r.status_code == 200
        data = r.json()["data"]
        # 默认兜底: 电费 10*0.8=8 + 服务费 10*0.5=5 = 13
        assert data["total_amount"] >= 13
        items = client._sesh.query(OrderFeeItem).filter(
            OrderFeeItem.order_id == order.id
        ).all()
        assert len(items) >= 1
        client._sesh.refresh(order)
        assert order.total_amount > 0

    def test_retry_charge_non_failed_rejected(self, client):
        """非 failed(completed) 订单 → 409 (状态机)。"""
        _seed_station(client._sesh, station_id=1)
        order = _seed_order(client._sesh, order_no="AB-OK",
                            status=OrderStatus.COMPLETED, charged_kwh=Decimal("10"))
        r = client.post(f"/api/v1/operate/orders/{order.id}/retry-charge")
        assert r.status_code == 409

    def test_retry_charge_cancelled_rejected(self, client):
        """cancelled 订单也不允许重试计费 → 409 (仅 failed)。"""
        _seed_station(client._sesh, station_id=1)
        order = _seed_order(client._sesh, order_no="AB-CANC",
                            status=OrderStatus.CANCELLED, charged_kwh=Decimal("10"))
        r = client.post(f"/api/v1/operate/orders/{order.id}/retry-charge")
        assert r.status_code == 409

    def test_retry_charge_idempotent(self, client):
        """重复重试 → 200, fee_items 不翻倍(幂等, settle 清旧重写)。"""
        _seed_station(client._sesh, station_id=1)
        order = _seed_order(client._sesh, order_no="AB-IDEMP2", charged_kwh=Decimal("10"))
        r1 = client.post(f"/api/v1/operate/orders/{order.id}/retry-charge")
        assert r1.status_code == 200
        r2 = client.post(f"/api/v1/operate/orders/{order.id}/retry-charge")
        assert r2.status_code == 200
        items = client._sesh.query(OrderFeeItem).filter(
            OrderFeeItem.order_id == order.id
        ).all()
        # 电费+服务费 = 2 条, 第二次清旧重写不翻倍
        assert len(items) == 2

    def test_retry_charge_not_found(self, client):
        """不存在订单 → 404。"""
        r = client.post("/api/v1/operate/orders/999999/retry-charge")
        assert r.status_code == 404


# ════════════════════════════════════════════════════════════
# team_scope: assert_order_team_access (与退款端点同源 helper)
# ════════════════════════════════════════════════════════════
class TestAbnormalOrderTeamScope:
    """resolve/retry-charge 写端点首行均调 assert_order_team_access, 团队隔离行为
    由该公共 helper 决定 —— 直接断言其语义即可覆盖 team_scope, 无需依赖 RBAC seed。"""

    def test_cross_team_denied_404(self, test_db):
        """非 admin 且订单属他团队 → 404 (不泄露存在)。"""
        session = test_db["session"]
        _seed_station(session, station_id=1, team_id=100)
        order = _seed_order(session, station_id=1)
        other = User(id=99, username="other", role=UserRole.OPERATOR,
                     team_id=200, status="active")
        with pytest.raises(HTTPException) as exc:
            assert_order_team_access(session, order.id, other)
        assert exc.value.status_code == 404

    def test_same_team_allowed(self, test_db):
        """非 admin 且同团队 → 不抛 (放行)。"""
        session = test_db["session"]
        _seed_station(session, station_id=1, team_id=100)
        order = _seed_order(session, station_id=1)
        same = User(id=88, username="same", role=UserRole.OPERATOR,
                    team_id=100, status="active")
        assert_order_team_access(session, order.id, same)  # 不抛即通过

    def test_admin_exempt(self, test_db):
        """admin 跨团队也放行 (平台级)。"""
        session = test_db["session"]
        _seed_station(session, station_id=1, team_id=100)
        order = _seed_order(session, station_id=1)
        admin = User(id=1, username="admin", role=UserRole.ADMIN,
                     team_id=999, status="active")
        assert_order_team_access(session, order.id, admin)  # 不抛即通过
