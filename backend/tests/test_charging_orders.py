"""
充电订单管理 API 测试 - Phase42

覆盖 backend/app/api/v1/charging_orders.py:
- GET    /api/v1/charging-orders               列表(多维筛选/分页/空数据)
- GET    /api/v1/charging-orders/{id}          详情(404)
- POST   /api/v1/charging-orders               创建(默认费率/活跃定价规则联动/折扣/缺必填)
- PUT    /api/v1/charging-orders/{id}/status   状态更新(正常completed|cancelled/无效/404)

计费联动: 无活跃定价规则时用默认费率(电价0.8, 服务费0.5)。
认证模式参考 test_fleet_settlement.py。
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture (覆盖 SessionLocal + seed admin)。每个测试独立 DB。"""
    pass


# ==========================================
# 折扣入口校验 (卡2230298e 缺口2) — ChargingOrderCreate.discount_amount 约束
# Pydantic ValidationError 是 FastAPI 422 的来源: body 校验失败 → 422。
# ==========================================

class TestCreateOrderDiscountValidation:
    """discount_amount 必须 >=0 且 <=100000 (百元级单位下足够宽松)。"""

    def test_negative_discount_rejected(self):
        """负折扣 → 422 (ValidationError)。"""
        from pydantic import ValidationError
        from app.api.v1.charging_orders import ChargingOrderCreate
        with pytest.raises(ValidationError):
            ChargingOrderCreate(station_id=1, device_id=1, discount_amount=-1.0)

    def test_oversized_discount_rejected(self):
        """超大折扣 (>100000) → 422。"""
        from pydantic import ValidationError
        from app.api.v1.charging_orders import ChargingOrderCreate
        with pytest.raises(ValidationError):
            ChargingOrderCreate(station_id=1, device_id=1, discount_amount=100001.0)

    def test_upper_bound_accepted(self):
        """上限边界 100000 合法 (闭区间)。"""
        from app.api.v1.charging_orders import ChargingOrderCreate
        req = ChargingOrderCreate(station_id=1, device_id=1, discount_amount=100000.0)
        assert req.discount_amount == 100000.0

    def test_normal_discount_accepted(self):
        """正常折扣不回归。"""
        from app.api.v1.charging_orders import ChargingOrderCreate
        req = ChargingOrderCreate(station_id=1, device_id=1, discount_amount=10.0)
        assert req.discount_amount == 10.0


def _auth_headers():
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    return {"Authorization": f"Bearer {token}"}


def _create_order(**overrides):
    """创建订单辅助。默认 charged_kwh=10 触发默认费率计费(电费10*0.8=8, 服务费10*0.5=5, total=13)。"""
    payload = {
        "station_id": 1,
        "device_id": 1,
        "charged_kwh": 10.0,
        "duration_minutes": 60,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/charging-orders", json=payload, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ═══════════════════════════════════════════════════════════════
# 创建 + 计费联动
# ═══════════════════════════════════════════════════════════════

def test_create_order_default_pricing():
    """默认费率计费: 电费10*0.8=8, 服务费10*0.5=5, total=13"""
    data = _create_order(charged_kwh=10.0)
    assert data["order_no"].startswith("CO")
    assert data["station_id"] == 1
    assert data["device_id"] == 1
    assert data["charged_kwh"] == 10.0
    assert data["electricity_fee"] == 8.0
    assert data["service_fee"] == 5.0
    assert data["total_amount"] == 13.0
    assert data["paid_amount"] == 13.0
    assert data["order_status"] == "pending"
    assert data["payment_status"] == "unpaid"


def test_create_order_with_active_pricing_rule():
    """有活跃定价规则时，用规则费率计费(电价1.0/服务费0.2 → 电费10, 服务费2)"""
    client.post("/api/v1/pricing", json={
        "name": "尖峰规则", "period_type": "peak",
        "start_time": "10:00", "end_time": "12:00",
        "electricity_price": 1.0, "service_fee_rate": 0.2,
        "is_active": True,
    }, headers=_auth_headers())

    data = _create_order(charged_kwh=10.0)
    assert data["electricity_fee"] == 10.0
    assert data["service_fee"] == 2.0
    assert data["total_amount"] == 12.0


def test_create_order_with_discount():
    """折扣抵扣: paid = total - discount = 13 - 3 = 10"""
    data = _create_order(charged_kwh=10.0, discount_amount=3.0)
    assert data["total_amount"] == 13.0
    assert data["discount_amount"] == 3.0
    assert data["paid_amount"] == 10.0


def test_create_order_with_parking_and_idle():
    """停车费 + 占用费计入总额(通过活跃定价规则配置费率)"""
    client.post("/api/v1/pricing", json={
        "name": "含停车占用", "period_type": "flat",
        "start_time": "10:00", "end_time": "12:00",
        "electricity_price": 0.8, "service_fee_rate": 0.5,
        "parking_fee_per_hour": 2.0, "idle_penalty_per_min": 0.5,
        "is_active": True,
    }, headers=_auth_headers())
    # 电费8 + 服务费5 + 停车2h*2.0=4 + 占用10min*0.5=5 = 22
    data = _create_order(charged_kwh=10.0, parking_duration_hours=2.0, idle_minutes=10)
    assert data["parking_fee"] == 4.0
    assert data["idle_penalty"] == 5.0
    assert data["total_amount"] == 22.0


def test_create_order_missing_required():
    """缺必填字段 station_id → 422"""
    resp = client.post("/api/v1/charging-orders", json={
        "device_id": 1, "charged_kwh": 10.0,
    }, headers=_auth_headers())
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 卡 c4cbcbf1: start_time ISO8601 解析 (py3.9 Z后缀500回归 + 坏值显式400)
# 旧实现: 裸 datetime.fromisoformat(body.start_time), py3.9 客户端传 Z →
# ValueError 冒泡全局 handler → 500; 坏值同样 500。接入共享 helper 收口。
# naive DateTime 列存 aware 值时 SQLAlchemy 剥 tzinfo 存墙钟 (与 on_call 同模式)。
# ═══════════════════════════════════════════════════════════════

def test_create_order_start_time_z_suffix():
    """start_time 带 'Z' 后缀 → 200, 墙钟回显 '2026-01-01T09:00:00'。

    py3.9 fromisoformat 不识 Z → 旧实现 500。
    """
    resp = client.post("/api/v1/charging-orders", json={
        "station_id": 1, "device_id": 1, "charged_kwh": 10.0,
        "start_time": "2026-01-01T09:00:00Z",
    }, headers=_auth_headers())
    assert resp.status_code == 200, f"Z后缀应200非500, 实际 {resp.status_code}: {resp.text}"
    assert resp.json()["data"]["start_time"] == "2026-01-01T09:00:00"


def test_create_order_start_time_offset():
    """start_time 显式 '+08:00' → 200, 墙钟回显 09:00。"""
    resp = client.post("/api/v1/charging-orders", json={
        "station_id": 1, "device_id": 1, "charged_kwh": 10.0,
        "start_time": "2026-01-01T09:00:00+08:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["start_time"] == "2026-01-01T09:00:00"


def test_create_order_start_time_naive():
    """start_time naive (无 tz) → 200, 回显 09:00。"""
    resp = client.post("/api/v1/charging-orders", json={
        "station_id": 1, "device_id": 1, "charged_kwh": 10.0,
        "start_time": "2026-01-01T09:00:00",
    }, headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["start_time"] == "2026-01-01T09:00:00"


def test_create_order_start_time_bad_value_400():
    """start_time 坏值 → 400 (用户输入错误), 非 500。

    旧实现裸 fromisoformat 抛 ValueError 冒泡全局 handler → 500。
    """
    resp = client.post("/api/v1/charging-orders", json={
        "station_id": 1, "device_id": 1, "charged_kwh": 10.0,
        "start_time": "not-a-date",
    }, headers=_auth_headers())
    assert resp.status_code == 400, f"坏值应400非500, 实际 {resp.status_code}: {resp.text}"


# ═══════════════════════════════════════════════════════════════
# 列表
# ═══════════════════════════════════════════════════════════════

def test_list_orders_and_filter():
    """列表 + 状态筛选 + 电站筛选"""
    _create_order(station_id=1)
    _create_order(station_id=2)

    resp = client.get("/api/v1/charging-orders", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] >= 2

    # 状态筛选(新订单均为 pending)
    resp = client.get("/api/v1/charging-orders?order_status=pending", headers=_auth_headers())
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) >= 2
    assert all(i["order_status"] == "pending" for i in items)

    # 电站筛选
    resp = client.get("/api/v1/charging-orders?station_id=1", headers=_auth_headers())
    assert resp.status_code == 200
    assert all(i["station_id"] == 1 for i in resp.json()["data"]["items"])


def test_list_orders_keyword_search():
    """订单编号模糊搜索"""
    data = _create_order()
    order_no = data["order_no"]
    # 用订单号的一部分做关键词
    keyword = order_no[-4:]
    resp = client.get(f"/api/v1/charging-orders?keyword={keyword}", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] >= 1


def test_list_orders_empty():
    """空数据列表"""
    resp = client.get("/api/v1/charging-orders", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []


def test_list_orders_pagination():
    """分页"""
    for _ in range(5):
        _create_order()
    resp = client.get("/api/v1/charging-orders?page=1&page_size=2", headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) == 2
    assert data["total"] >= 5


# ═══════════════════════════════════════════════════════════════
# 详情
# ═══════════════════════════════════════════════════════════════

def test_get_order_detail():
    data = _create_order()
    oid = data["id"]
    resp = client.get(f"/api/v1/charging-orders/{oid}", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == oid
    assert resp.json()["data"]["order_no"] == data["order_no"]


def test_get_order_not_found():
    resp = client.get("/api/v1/charging-orders/99999", headers=_auth_headers())
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 状态更新
# ═══════════════════════════════════════════════════════════════

def test_update_order_status_completed():
    """completed → 设置 end_time"""
    data = _create_order()
    oid = data["id"]
    resp = client.put(f"/api/v1/charging-orders/{oid}/status",
                      json={"status": "completed"}, headers=_auth_headers())
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["order_status"] == "completed"
    assert d["end_time"] is not None


def test_update_order_status_cancelled():
    """cancelled → 设置 end_time"""
    data = _create_order()
    oid = data["id"]
    resp = client.put(f"/api/v1/charging-orders/{oid}/status",
                      json={"status": "cancelled"}, headers=_auth_headers())
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["order_status"] == "cancelled"
    assert d["end_time"] is not None


def test_update_order_invalid_status():
    """无效状态 → 400"""
    data = _create_order()
    oid = data["id"]
    resp = client.put(f"/api/v1/charging-orders/{oid}/status",
                      json={"status": "invalid_status"}, headers=_auth_headers())
    # 卡 77a186b3：status 已收紧为 Literal，非法值在 Pydantic 层即被拒（422）
    assert resp.status_code == 422


def test_update_order_status_not_found():
    resp = client.put("/api/v1/charging-orders/99999/status",
                      json={"status": "completed"}, headers=_auth_headers())
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 认证
# ═══════════════════════════════════════════════════════════════

def test_unauthorized_request_rejected():
    """无 token 访问受保护端点 → 401/403"""
    client.headers.pop("Authorization", None)  # 清除 autouse 注入的 admin token，测真匿名拒绝
    resp = client.get("/api/v1/charging-orders")
    assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════
# 事务原子性 (卡b8895972) — 订单与费用同一提交边界
# ═══════════════════════════════════════════════════════════════

class TestCreateOrderAtomicity:
    """settle_order_fees 异常时订单不得落库(原缺陷: 首个commit先落订单, 费用失败留下光杆订单)。"""

    def test_settle_failure_rolls_back_order(self, monkeypatch):
        """mock settle_order_fees 抛异常 → ChargingOrder 表数量不变"""
        from app.core.database import SessionLocal as _sl  # noqa: F401
        from app.api.v1 import charging_orders as route_mod
        from app.services import billing_engine

        def _boom(*a, **kw):
            raise ValueError("settle boom")

        monkeypatch.setattr(billing_engine, "settle_order_fees", _boom)

        from app.models.charging_order import ChargingOrder
        with _test_session() as before:
            count_before = before.query(ChargingOrder).count()

        resp = client.post("/api/v1/charging-orders",
                           json={"station_id": 1, "device_id": 1,
                                 "charged_kwh": 10.0, "duration_minutes": 60},
                           headers=_auth_headers())
        assert resp.status_code == 500, resp.text

        with _test_session() as after:
            assert after.query(ChargingOrder).count() == count_before

    def test_create_order_persists_order_and_fee_items(self):
        """正常路径: 订单落库 + OrderFeeItem 明细 + 5项费用字段已写"""
        from app.core.database import SessionLocal
        from app.models.charging_order import ChargingOrder
        from app.models.order_fee_item import OrderFeeItem

        data = _create_order(charged_kwh=10.0)
        session = SessionLocal()
        try:
            order = session.query(ChargingOrder).filter_by(id=data["id"]).one()
            assert order.electricity_fee == 8.0
            assert order.service_fee == 5.0
            assert order.parking_fee == 0.0
            assert order.occupancy_fee == 0.0
            assert order.reservation_fee == 0.0
            items = session.query(OrderFeeItem).filter_by(order_id=order.id).all()
            assert len(items) >= 2  # 电费 + 服务费明细
            assert {i.fee_type.value for i in items} >= {"electricity", "service"}
        finally:
            session.close()


def _test_session():
    """独立会话(绕过请求事务, 直查落库状态)。"""
    from app.core.database import SessionLocal

    class _Ctx:
        def __enter__(self):
            self.s = SessionLocal()
            return self.s

        def __exit__(self, *a):
            self.s.close()

    return _Ctx()
