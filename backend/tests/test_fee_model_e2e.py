"""
费用模型端到端集成测试 — 五项费用全链路结算

与 test_order_fees.py 的差异:
- test_order_fees.py 直接调用 settle_order()/create_refund() 等函数 (函数级集成)
- 本套件走 HTTP TestClient 全链路: 经过路由解析 → get_current_user 认证 →
  Pydantic 校验 → 业务逻辑 → DB 落库, 验证真实 API 行为。

覆盖场景 (对应 SPEC 五项费用 + 退款):
1. 充电费+服务费结算: 分时电价(尖峰/平/谷/深谷) → 结算 → fee_items 明细 + 订单字段写入
2. 停车费计算: 充电结束后停留 → 停车费 = 时长 × 费率
3. 占桩费: 免罚期内(occupancy=0)不收 vs 超时(occupancy>0)收取
4. 预约费: 到场释放(reservation=0)不收 vs 爽约(reservation>0)扣除
5. 优惠抵扣: 折扣+优惠券+积分 → 实收 = 总费用 - 抵扣
6. 退款全流程: 申请 → 审批 → 到账 → 订单状态变更 (HTTP 全链路)
+ 退款拒绝分支、认证边界 (401)

说明: 当前结算 API (order_fees.settle_order) 按已算好的时长/费率做乘法,
"免罚倒计时""押金冻结""原路退回渠道"等设备/支付侧语义在 API 层体现为:
占桩/预约时长为 0 则不收费、退款状态机推进到 refunded。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.charging_order import (
    ChargingOrder, OrderPaymentStatus, OrderStatus,
)

# 复用全局 app (路由用 app.core.database.get_db → SessionLocal)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db: 覆盖模块级 SessionLocal + seed admin。每个测试独立 DB。"""
    pass


# ─── 辅助函数 ───

# SettleRequest 所有字段都有默认值, 这里给出全 0 基线, 测试按需覆盖
_SETTLE_DEFAULTS = dict(
    peak_energy=0.0, flat_energy=0.0, valley_energy=0.0, trough_energy=0.0,
    peak_price=0.0, flat_price=0.0, valley_price=0.0, trough_price=0.0,
    service_fee_rate=0.0,
    parking_hours=0.0, parking_rate=0.0,
    occupancy_minutes=0, occupancy_rate=0.0,
    reservation_minutes=0, reservation_rate=0.0,
    discount_amount=0.0, coupon_amount=0.0, points_amount=0.0,
)

_order_seq = [0]


def _auth_headers():
    """登录 admin 拿 Bearer token (order_fees router 受 get_current_user 保护)。"""
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    assert token, f"未取到 token: {data}"
    return {"Authorization": f"Bearer {token}"}


def _seed_order(test_db, **overrides):
    """用 session 直接准备订单 (精确控制初始支付/订单状态)。"""
    _order_seq[0] += 1
    defaults = dict(
        order_no=f"E2E-FEE-{_order_seq[0]:04d}",
        station_id=1, device_id=1, user_id=1,
        charged_kwh=0,
        total_amount=0, paid_amount=0,
        payment_status=OrderPaymentStatus.UNPAID,
        order_status=OrderStatus.PENDING,
    )
    defaults.update(overrides)
    session = test_db["session"]
    order = ChargingOrder(**defaults)
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def _reload_order(test_db, order_id):
    """重新查询订单 (HTTP 用独立 session 提交, 需 expire 本地缓存才能读到最新值)。"""
    session = test_db["session"]
    session.expire_all()
    return session.query(ChargingOrder).filter(ChargingOrder.id == order_id).first()


def _settle(order_id, **overrides):
    """POST 结算, 返回 data。"""
    payload = dict(_SETTLE_DEFAULTS)
    payload.update(overrides)
    r = client.post(
        f"/api/v1/orders/{order_id}/settle",
        json=payload,
        headers=_auth_headers(),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _fee_items(order_id):
    """GET 费用明细, 返回 list。"""
    r = client.get(f"/api/v1/orders/{order_id}/fee-items", headers=_auth_headers())
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _amount_by_type(items, fee_type):
    """从 fee_items 中取指定 fee_type 的金额之和。"""
    return sum(i["amount"] for i in items if i["fee_type"] == fee_type)


# ═══════════════════════════════════════════════════════
# 结算全链路 E2E
# ═══════════════════════════════════════════════════════

class TestSettlementFlowE2E:
    """五项费用结算 — HTTP 全链路"""

    def test_charge_and_service_fee_with_tou_pricing(self, test_db):
        """充电费(分时尖峰平谷深谷) + 服务费结算, 验证 fee_items 明细与订单字段。"""
        order = _seed_order(test_db)

        # 尖峰20@1.0 + 平15@0.7 + 谷10@0.4 + 深谷5@0.2 = 20+10.5+4+1 = 35.5
        # 服务费 = 50kWh × 0.5 = 25 ; 总费用 = 35.5 + 25 = 60.5
        data = _settle(
            order.id,
            peak_energy=20, flat_energy=15, valley_energy=10, trough_energy=5,
            peak_price=1.0, flat_price=0.7, valley_price=0.4, trough_price=0.2,
            service_fee_rate=0.5,
        )

        # 4 条分时电费 + 1 条服务费 = 5 行
        assert len(data["fee_items"]) == 5
        assert _amount_by_type(data["fee_items"], "electricity") == pytest.approx(35.5)
        assert _amount_by_type(data["fee_items"], "service") == pytest.approx(25.0)
        assert data["total_amount"] == pytest.approx(60.5)
        assert data["paid_amount"] == pytest.approx(60.5)  # 无优惠

        # 订单字段被写入: charged_kwh=50, electricity_fee=35.5, service_fee=25
        order = _reload_order(test_db, order.id)
        assert float(order.charged_kwh) == pytest.approx(50.0)
        assert float(order.electricity_fee) == pytest.approx(35.5)
        assert float(order.service_fee) == pytest.approx(25.0)

        # fee-items 端点能查到落库的明细
        items = _fee_items(order.id)
        assert len(items) == 5
        names = {i["fee_name"] for i in items}
        assert "尖峰电费" in names and "平段电费" in names
        assert "谷段电费" in names and "深谷电费" in names
        assert "服务费" in names

    def test_parking_fee_calculation(self, test_db):
        """停车费: 充电结束后停留 1.5 小时 × 4 元/小时 = 6 元。"""
        order = _seed_order(test_db)

        # 平段10@0.8=8, 服务费 10×0.5=5, 停车 1.5×4=6 ; 总=8+5+6=19
        data = _settle(
            order.id,
            flat_energy=10, flat_price=0.8,
            service_fee_rate=0.5,
            parking_hours=1.5, parking_rate=4.0,
        )

        parking_items = [i for i in data["fee_items"] if i["fee_type"] == "parking"]
        assert len(parking_items) == 1
        assert parking_items[0]["amount"] == pytest.approx(6.0)
        assert parking_items[0]["quantity"] == pytest.approx(1.5)
        assert parking_items[0]["unit_price"] == pytest.approx(4.0)
        assert parking_items[0]["unit"] == "小时"
        assert data["total_amount"] == pytest.approx(19.0)

        order = _reload_order(test_db, order.id)
        assert float(order.parking_fee) == pytest.approx(6.0)

    def test_occupancy_fee_grace_period_vs_overtime(self, test_db):
        """占桩费: 免罚期内(0分钟)不收, 超时(60分钟)按 0.5元/分钟 收 30 元。"""
        # 场景A: 充电完成在免罚期内拔枪 → 不产生占桩费
        order_a = _seed_order(test_db)
        data_a = _settle(
            order_a.id,
            flat_energy=10, flat_price=0.8, service_fee_rate=0.5,
            occupancy_minutes=0, occupancy_rate=0.5,
        )
        assert _amount_by_type(data_a["fee_items"], "occupancy") == 0
        assert not any(i["fee_type"] == "occupancy" for i in data_a["fee_items"])

        # 场景B: 充电完成未拔枪, 超过免罚期 60 分钟 → 占桩费 60×0.5=30
        order_b = _seed_order(test_db)
        data_b = _settle(
            order_b.id,
            flat_energy=10, flat_price=0.8, service_fee_rate=0.5,
            occupancy_minutes=60, occupancy_rate=0.5,
        )
        occ_items = [i for i in data_b["fee_items"] if i["fee_type"] == "occupancy"]
        assert len(occ_items) == 1
        assert occ_items[0]["amount"] == pytest.approx(30.0)
        assert occ_items[0]["unit"] == "分钟"
        # 总费用 = 电费8 + 服务费5 + 占桩30 = 43
        assert data_b["total_amount"] == pytest.approx(43.0)

        order_b = _reload_order(test_db, order_b.id)
        assert float(order_b.occupancy_fee) == pytest.approx(30.0)
        assert float(order_b.idle_penalty) == pytest.approx(30.0)  # 兼容旧字段同步

    def test_reservation_fee_arrive_vs_no_show(self, test_db):
        """预约费: 到场释放(0分钟)不收, 爽约(30分钟)按 0.5元/分钟 扣 15 元。"""
        # 场景A: 预约后按时到场 → 释放, 不收预约费
        order_a = _seed_order(test_db)
        data_a = _settle(
            order_a.id,
            flat_energy=10, flat_price=0.8, service_fee_rate=0.5,
            reservation_minutes=0, reservation_rate=0.5,
        )
        assert _amount_by_type(data_a["fee_items"], "reservation") == 0

        # 场景B: 预约后爽约 → 预约时长 30 分钟计费 30×0.5=15
        order_b = _seed_order(test_db)
        data_b = _settle(
            order_b.id,
            flat_energy=10, flat_price=0.8, service_fee_rate=0.5,
            reservation_minutes=30, reservation_rate=0.5,
        )
        rv_items = [i for i in data_b["fee_items"] if i["fee_type"] == "reservation"]
        assert len(rv_items) == 1
        assert rv_items[0]["amount"] == pytest.approx(15.0)
        # 总费用 = 电费8 + 服务费5 + 预约15 = 28
        assert data_b["total_amount"] == pytest.approx(28.0)

        order_b = _reload_order(test_db, order_b.id)
        assert float(order_b.reservation_fee) == pytest.approx(15.0)

    def test_discount_coupon_points_deduction(self, test_db):
        """优惠抵扣: 折扣20+券15+积分10, 实收 = 总费用150 - 抵扣45 = 105。"""
        order = _seed_order(test_db)

        # 平段100@1.0=100, 服务费 100×0.5=50 ; 总费用=150
        # 实收 = 150 - 20(折扣) - 15(券) - 10(积分) = 105
        data = _settle(
            order.id,
            flat_energy=100, flat_price=1.0,
            service_fee_rate=0.5,
            discount_amount=20.0, coupon_amount=15.0, points_amount=10.0,
        )

        # 1 电费 + 1 服务费 + 3 优惠行 = 5 行
        assert len(data["fee_items"]) == 5
        # 优惠行 amount 为负 (抵扣)
        assert _amount_by_type(data["fee_items"], "discount") == pytest.approx(-20.0)
        assert _amount_by_type(data["fee_items"], "coupon") == pytest.approx(-15.0)
        assert _amount_by_type(data["fee_items"], "points") == pytest.approx(-10.0)

        assert data["total_amount"] == pytest.approx(150.0)
        assert data["paid_amount"] == pytest.approx(105.0)

        order = _reload_order(test_db, order.id)
        assert float(order.discount_amount) == pytest.approx(20.0)
        assert float(order.coupon_amount) == pytest.approx(15.0)
        assert float(order.points_amount) == pytest.approx(10.0)
        assert float(order.paid_amount) == pytest.approx(105.0)

    def test_settle_requires_authentication(self, test_db):
        """认证边界: 不带 Bearer token 调用结算 → 401。"""
        order = _seed_order(test_db)
        client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
        r = client.post(f"/api/v1/orders/{order.id}/settle", json={})
        assert r.status_code == 401

    def test_settle_unknown_order_returns_404(self, test_db):
        """结算不存在的订单 → 404。"""
        r = client.post(
            "/api/v1/orders/999999/settle",
            json=dict(_SETTLE_DEFAULTS, flat_energy=10, flat_price=0.8),
            headers=_auth_headers(),
        )
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════
# 退款全链路 E2E
# ═══════════════════════════════════════════════════════

class TestRefundFlowE2E:
    """退款流程 — 申请 → 审批 → 到账 / 拒绝 (HTTP 全链路)"""

    def _seed_paid_order(self, test_db, paid=100.0):
        return _seed_order(
            test_db,
            charged_kwh=50,
            total_amount=paid, paid_amount=paid,
            payment_status=OrderPaymentStatus.PAID,
            order_status=OrderStatus.COMPLETED,
        )

    def test_full_refund_approve_and_complete(self, test_db):
        """退款全流程: 申请(pending) → 审批(approved) → 到账(refunded), 订单状态联动。"""
        order = self._seed_paid_order(test_db, paid=100.0)

        # 1. 发起退款申请 (全额 100, complete 后累计==实付 → REFUNDED)
        r = client.post(
            f"/api/v1/orders/{order.id}/refund",
            json={"refund_amount": 100.0, "reason": "多收费用"},
            headers=_auth_headers(),
        )
        assert r.status_code == 200, r.text
        refund = r.json()["data"]
        assert refund["status"] == "pending"
        assert refund["refund_amount"] == pytest.approx(100.0)
        refund_id = refund["id"]

        # 订单进入退款中
        assert _reload_order(test_db, order.id).payment_status == OrderPaymentStatus.REFUNDING

        # 2. 审批通过 (缺陷3: reviewer_id 取 token; body.reviewer_id=999 应被忽略)
        r = client.post(
            f"/api/v1/orders/{order.id}/refunds/{refund_id}/approve",
            json={"reviewer_id": 999},
            headers=_auth_headers(),
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "approved"
        # 落 admin user.id (=1), 非 body 的 999
        assert r.json()["data"]["reviewer_id"] == 1

        # 3. 标记已退款 (原路退回到账)
        r = client.post(
            f"/api/v1/orders/{order.id}/refunds/{refund_id}/complete",
            headers=_auth_headers(),
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "refunded"

        # 订单变为已退款
        assert _reload_order(test_db, order.id).payment_status == OrderPaymentStatus.REFUNDED

        # 退款记录列表可查
        r = client.get(f"/api/v1/orders/{order.id}/refunds", headers=_auth_headers())
        assert r.status_code == 200
        assert len(r.json()["data"]) == 1

    def test_refund_rejected_restores_paid(self, test_db):
        """退款被拒 → 订单恢复已支付, 拒绝原因落库。"""
        order = self._seed_paid_order(test_db, paid=100.0)

        r = client.post(
            f"/api/v1/orders/{order.id}/refund",
            json={"refund_amount": 40.0, "reason": "测试拒绝"},
            headers=_auth_headers(),
        )
        assert r.status_code == 200, r.text
        refund_id = r.json()["data"]["id"]
        assert _reload_order(test_db, order.id).payment_status == OrderPaymentStatus.REFUNDING

        r = client.post(
            f"/api/v1/orders/{order.id}/refunds/{refund_id}/reject",
            json={"reviewer_id": 1, "reject_reason": "不符合退款条件"},
            headers=_auth_headers(),
        )
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        assert body["status"] == "rejected"
        assert body["reject_reason"] == "不符合退款条件"

        # 订单支付状态恢复为已支付
        assert _reload_order(test_db, order.id).payment_status == OrderPaymentStatus.PAID

    def test_refund_exceeds_paid_rejected(self, test_db):
        """退款金额超过实付 → 400。"""
        order = self._seed_paid_order(test_db, paid=50.0)
        r = client.post(
            f"/api/v1/orders/{order.id}/refund",
            json={"refund_amount": 200.0, "reason": "超额退款"},
            headers=_auth_headers(),
        )
        assert r.status_code == 400
