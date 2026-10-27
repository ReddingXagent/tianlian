"""
订单退款 API 测试 (app/api/v1/order_fees.py) — 补全 refund 链路三端点

覆盖端点 (前缀 /api/v1, router 依赖 get_current_user + require_write_permission("charging:manage")):
  - POST /orders/{order_id}/refund                          发起退款申请 (create_refund)
  - GET  /orders/{order_id}/refunds                          查看退款记录 (list_refunds)
  - POST /orders/{order_id}/refunds/{refund_id}/approve      审批退款 (approve_refund)

测试矩阵:
  ① happy path: 发起退款落 PENDING + 订单转 REFUNDING; 列表回查; approve 乐观锁推进 PENDING→APPROVED
  ② error path: 订单不存在 404; 未支付订单不可退款 400; 退款超额 400; approve 不存在/已变更 404/409

风格同 test_supervision.py: client 默认 admin (平台级, assert_order_team_access 豁免),
直接 seed ORM (ChargingOrder / RefundRecord) 到 client._sesh, 与端点 get_db 共享同一测试库。

铁律: 仅加测试, 不改业务代码。
"""
from datetime import datetime, timezone
from decimal import Decimal

from app.models.charging_order import ChargingOrder, OrderPaymentStatus
from app.models.order_fee_item import RefundRecord, RefundStatus


# ─── seed helpers ───

def _seed_order(session, payment_status=OrderPaymentStatus.PAID,
                paid_amount=Decimal("100.00"), station_id=1, device_id=1, user_id=1,
                order_no="TL-REFUND-1"):
    """直接 seed 一条充电订单。

    station_id / device_id 给固定值 (SQLite 不强制外键, 仅需满足 nullable=False);
    paid_amount / payment_status 决定能否退款 (create_refund 仅允许 PAID/PARTIAL)。
    """
    order = ChargingOrder(
        order_no=order_no,
        station_id=station_id,
        device_id=device_id,
        user_id=user_id,
        paid_amount=paid_amount,
        payment_status=payment_status,
        total_amount=paid_amount,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def _seed_refund(session, order_id, amount=Decimal("50.00"), status=RefundStatus.PENDING,
                 user_id=1, reason="测试退款", prev_payment_status="paid"):
    """直接 seed 一条退款记录 (用于 approve 用例构造前置状态)。"""
    refund = RefundRecord(
        order_id=order_id,
        user_id=user_id,
        refund_amount=amount,
        reason=reason,
        status=status,
        prev_payment_status=prev_payment_status,
    )
    session.add(refund)
    session.commit()
    session.refresh(refund)
    return refund


# ==================== create_refund: POST /orders/{order_id}/refund ====================

class TestCreateRefund:
    """发起退款申请: happy (落 PENDING + 订单转 REFUNDING) / error (404 / 400 未支付 / 400 超额)。"""

    def test_create_refund_happy_pending_and_order_refunding(self, client):
        """PAID 订单发起退款 → 200, 记录 PENDING, prev_payment_status 快照 paid, 订单转 REFUNDING。"""
        order = _seed_order(client._sesh, payment_status=OrderPaymentStatus.PAID,
                            paid_amount=Decimal("100.00"))
        r = client.post(f"/api/v1/orders/{order.id}/refund",
                        json={"refund_amount": 30, "reason": "用户投诉"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["order_id"] == order.id
        assert d["status"] == "pending"
        assert d["refund_amount"] == 30.0
        assert d["reason"] == "用户投诉"
        # 卡 aa88371f 缺陷2: 快照退款前支付状态
        assert d["prev_payment_status"] == "paid"
        assert d["reviewer_id"] is None  # 待审批

        # 订单支付状态已转 REFUNDING
        client._sesh.expire_all()
        refreshed = client._sesh.query(ChargingOrder).filter(ChargingOrder.id == order.id).first()
        assert refreshed.payment_status == OrderPaymentStatus.REFUNDING

    def test_create_refund_partial_order_allowed(self, client):
        """PARTIAL 状态订单也可发起退款 (允许 PAID/PARTIAL)。"""
        order = _seed_order(client._sesh, payment_status=OrderPaymentStatus.PARTIAL,
                            paid_amount=Decimal("80.00"))
        r = client.post(f"/api/v1/orders/{order.id}/refund",
                        json={"refund_amount": 10, "reason": "部分退"})
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "pending"

    def test_create_refund_order_not_found_404(self, client):
        r = client.post("/api/v1/orders/999999/refund",
                        json={"refund_amount": 10, "reason": "x"})
        assert r.status_code == 404
        assert "不存在" in r.json()["detail"]

    def test_create_refund_unpaid_order_400(self, client):
        """UNPAID 订单不可退款 (端点仅放行 PAID/PARTIAL)。"""
        order = _seed_order(client._sesh, payment_status=OrderPaymentStatus.UNPAID,
                            paid_amount=Decimal("0.00"))
        r = client.post(f"/api/v1/orders/{order.id}/refund",
                        json={"refund_amount": 10, "reason": "x"})
        assert r.status_code == 400
        assert "未支付" in r.json()["detail"]

    def test_create_refund_exceeds_paid_400(self, client):
        """退款金额超过实付 → 400。"""
        order = _seed_order(client._sesh, payment_status=OrderPaymentStatus.PAID,
                            paid_amount=Decimal("50.00"))
        r = client.post(f"/api/v1/orders/{order.id}/refund",
                        json={"refund_amount": 80, "reason": "超额退"})
        assert r.status_code == 400
        assert "超过" in r.json()["detail"]

    def test_create_refund_zero_amount_422(self, client):
        """refund_amount <= 0 触发 pydantic gt=0 → 422。"""
        order = _seed_order(client._sesh)
        r = client.post(f"/api/v1/orders/{order.id}/refund",
                        json={"refund_amount": 0, "reason": "x"})
        assert r.status_code == 422


# ==================== list_refunds: GET /orders/{order_id}/refunds ====================

class TestListRefunds:
    """查看退款记录: happy (多条回查) / error (订单不存在 404)。"""

    def test_list_refunds_returns_all_for_order(self, client):
        order = _seed_order(client._sesh, paid_amount=Decimal("200.00"))
        _seed_refund(client._sesh, order.id, amount=Decimal("30.00"), reason="第一笔")
        _seed_refund(client._sesh, order.id, amount=Decimal("50.00"), reason="第二笔")
        r = client.get(f"/api/v1/orders/{order.id}/refunds")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert len(data) == 2
        amounts = {item["refund_amount"] for item in data}
        assert amounts == {30.0, 50.0}
        assert all(item["order_id"] == order.id for item in data)

    def test_list_refunds_empty_for_order(self, client):
        """无退款记录 → 200 空列表。"""
        order = _seed_order(client._sesh)
        r = client.get(f"/api/v1/orders/{order.id}/refunds")
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_list_refunds_order_not_found_404(self, client):
        r = client.get("/api/v1/orders/999999/refunds")
        assert r.status_code == 404


# ==================== approve_refund: POST /orders/{order_id}/refunds/{refund_id}/approve ====================

class TestApproveRefund:
    """审批退款: happy (PENDING→APPROVED, reviewer_id 取 token user) / error (404 / 409 已变更)。"""

    def test_approve_refund_happy_pending_to_approved(self, client):
        """PENDING → APPROVED, reviewer_id 取 token(user.id), reviewed_at 已置。"""
        order = _seed_order(client._sesh)
        refund = _seed_refund(client._sesh, order.id, status=RefundStatus.PENDING)
        r = client.post(f"/api/v1/orders/{order.id}/refunds/{refund.id}/approve", json={})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["id"] == refund.id
        assert d["status"] == "approved"
        # 卡 aa88371f 缺陷3: reviewer_id 取 token(user.id=admin), 非 body
        assert d["reviewer_id"] is not None
        assert d["reviewed_at"] is not None

    def test_approve_refund_records_token_reviewer_not_body(self, client):
        """body.reviewer_id 已废弃 — 服务端始终用 token user.id。"""
        order = _seed_order(client._sesh)
        refund = _seed_refund(client._sesh, order.id, status=RefundStatus.PENDING)
        # 故意传一个假的 reviewer_id, 应被忽略
        r = client.post(f"/api/v1/orders/{order.id}/refunds/{refund.id}/approve",
                        json={"reviewer_id": 99999})
        assert r.status_code == 200
        # reviewer_id 应为 admin (token user), 而非 99999
        assert r.json()["data"]["reviewer_id"] != 99999

    def test_approve_refund_not_found_404(self, client):
        """退款记录不存在 → 404。"""
        order = _seed_order(client._sesh)
        r = client.post(f"/api/v1/orders/{order.id}/refunds/999999/approve", json={})
        assert r.status_code == 404
        assert "不存在" in r.json()["detail"]

    def test_approve_refund_already_approved_409(self, client):
        """已 APPROVED 的退款再次 approve → 乐观锁拦截 409 (非 PENDING 不可推进)。"""
        order = _seed_order(client._sesh)
        refund = _seed_refund(client._sesh, order.id, status=RefundStatus.APPROVED)
        r = client.post(f"/api/v1/orders/{order.id}/refunds/{refund.id}/approve", json={})
        assert r.status_code == 409
        assert "已变更" in r.json()["detail"]

    def test_approve_refund_idempotent_second_call_409(self, client):
        """同一 PENDING 退款第二次 approve → 409 (第一次已推进到 APPROVED)。"""
        order = _seed_order(client._sesh)
        refund = _seed_refund(client._sesh, order.id, status=RefundStatus.PENDING)
        first = client.post(f"/api/v1/orders/{order.id}/refunds/{refund.id}/approve", json={})
        assert first.status_code == 200
        second = client.post(f"/api/v1/orders/{order.id}/refunds/{refund.id}/approve", json={})
        assert second.status_code == 409
