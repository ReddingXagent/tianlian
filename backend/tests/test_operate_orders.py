"""
运营-订单管理 API 测试 (卡 e5c2c9ec — 全端点覆盖扩展)

覆盖 /api/v1/operate/orders 的全部只读端点:
- GET /orders                 订单列表(状态/支付状态/站点/关键字/日期/分页 过滤)
- GET /orders/enterprise      企业充电订单
- GET /orders/vehicle         车辆充电订单(按车牌)
- GET /orders/{id}            订单详情(5项费用拆解 + fee_items)
- GET /orders/{id}/charge-curve  订单充电曲线时间序列

写端点 POST /orders/{id}/resolve 与 POST /orders/{id}/retry-charge 由
tests/test_operate_order_actions.py 专门覆盖(resolve 标记/幂等/422/404、
retry 状态机/幂等/404、team_scope helper), 本文件不重复, 聚焦只读查询矩阵。

team 隔离: list/enterprise/vehicle 经 is_platform_admin + Station.team_id 过滤;
detail/curve 经公共 helper assert_order_team_access。default client 为 admin
(平台级, 豁免 team scoping), 故正常路径断言全量; 团队级隔离行为以 test_db +
直接构造非 admin User + 直接调 helper 覆盖(与 test_operate_order_actions.py
同惯例, 规避 RBAC seed 依赖)。
"""
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException

# 先经 order_fees 入口触发 app.api.v1 完整加载, 规避 deps ↔ api.v1.__init__ 循环 import
# (与 test_operate_order_actions.py 同 import 惯例)。
from app.api.v1.order_fees import router as _order_fees_router  # noqa: F401
from app.api.deps import (
    assert_order_team_access,
    assert_enterprise_team_access,
    assert_station_team_access,
)
from app.models.charging_order import (
    ChargingOrder, OrderStatus, OrderPaymentStatus, PaymentMethod, UserType,
)
from app.models.order_fee_item import OrderFeeItem, FeeType
from app.models.spec_tables import OrderChargeCurve
from app.models.station import Station
from app.models.user import User, UserRole


# ─── 种子数据 ───

def _seed_orders(session):
    """3 笔不同订单号/车牌的订单 (挂 station 1/2, team 由调用方设定)。"""
    session.add_all([
        Station(id=1, name="一号站", code="ST001", team_id=100),
        Station(id=2, name="二号站", code="ST002", team_id=200),
    ])
    session.add_all([
        ChargingOrder(
            order_no="ORD001", station_id=1, device_id=1, user_id=101,
            user_type=UserType.APP, plate_number="京A12345",
            charged_kwh="50.00", total_amount="100.00", paid_amount="100.00",
            payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.WECHAT, duration_minutes=60,
        ),
        ChargingOrder(
            order_no="ORD002", station_id=1, device_id=2, user_id=102,
            user_type=UserType.CARD, plate_number="京B66666",
            total_amount="0", paid_amount="0",
            payment_status=OrderPaymentStatus.UNPAID, order_status=OrderStatus.PENDING,
        ),
        ChargingOrder(
            order_no="VIP999", station_id=2, device_id=3, user_id=103,
            user_type=UserType.APP, plate_number="沪C88888",
            charged_kwh="80.00", total_amount="120.00", paid_amount="120.00",
            payment_status=OrderPaymentStatus.PAID, order_status=OrderStatus.COMPLETED,
            payment_method=PaymentMethod.ALIPAY, duration_minutes=90,
        ),
    ])
    session.commit()


def _seed_curve(session, order_id: int = 5001):
    """3 条曲线点 — 故意乱序 record_time 写入, 用于验证端点按时间升序返回"""
    session.add_all([
        OrderChargeCurve(
            order_id=order_id, record_time=datetime(2026, 7, 21, 10, 2, 0),
            current_power=Decimal("90.00"), energy_this_minute=Decimal("1.5000"),
            voltage=Decimal("400.00"), current=Decimal("225.00"), soc=Decimal("22.00"),
        ),
        OrderChargeCurve(
            order_id=order_id, record_time=datetime(2026, 7, 21, 10, 0, 0),
            current_power=Decimal("30.00"), energy_this_minute=Decimal("0.5000"),
            voltage=Decimal("400.00"), current=Decimal("75.00"), soc=Decimal("20.00"),
        ),
        OrderChargeCurve(
            order_id=order_id, record_time=datetime(2026, 7, 21, 10, 1, 0),
            current_power=Decimal("60.00"), energy_this_minute=Decimal("1.0000"),
            voltage=Decimal("400.00"), current=Decimal("150.00"), soc=Decimal("21.00"),
        ),
    ])
    session.commit()


def _seed_curve_with_nulls(session, order_id: int = 5002):
    """含 None 字段的曲线点 — 验证 None → JSON null (不抛 AttributeError)。"""
    session.add(OrderChargeCurve(
        order_id=order_id, record_time=datetime(2026, 7, 21, 11, 0, 0),
        current_power=None, energy_this_minute=None, voltage=None, current=None, soc=None,
    ))
    session.commit()


# ════════════════════════════════════════════════════════════
# GET /orders — 订单列表
# ════════════════════════════════════════════════════════════
class TestListOrders:
    """订单列表: 关键字/状态/支付状态/站点/日期/分页 过滤 + 参数校验 + 鉴权。"""

    def test_list_orders_and_keyword(self, client):
        """列表返回全部 + 订单号搜索命中"""
        _seed_orders(client._sesh)

        data = client.get("/api/v1/operate/orders").json()["data"]
        assert data["total"] >= 3

        searched = client.get("/api/v1/operate/orders?keyword=ORD001").json()["data"]
        assert searched["total"] == 1
        assert searched["items"][0]["order_no"] == "ORD001"

    def test_list_orders_search_by_plate(self, client):
        """车牌号模糊搜索"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders?keyword=沪C").json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["plate_number"] == "沪C88888"

    def test_list_orders_filter_by_station(self, client):
        """station_id 过滤"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders?station_id=2").json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["order_no"] == "VIP999"

    def test_list_orders_filter_by_status(self, client):
        """order_status 字符串值过滤 → 仅返回匹配状态"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders?status=completed").json()["data"]
        assert data["total"] == 2
        assert all(it["order_status"] == "completed" for it in data["items"])

    def test_list_orders_filter_by_payment_status(self, client):
        """payment_status 字符串值过滤 → 仅返回已支付"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders?payment_status=paid").json()["data"]
        assert data["total"] == 2
        assert all(it["payment_status"] == "paid" for it in data["items"])

    def test_list_orders_filter_by_unpaid(self, client):
        """payment_status=unpaid → 仅 1 笔待支付"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders?payment_status=unpaid").json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["order_no"] == "ORD002"

    def test_list_orders_start_date_excludes_old(self, client):
        """start_date 未来值 → 排除全部(创建时间早于未来)"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders?start_date=2099-01-01").json()["data"]
        assert data["total"] == 0

    def test_list_orders_end_date_past_excludes_all(self, client):
        """end_date 过去值 → 排除全部(created_at >= 远早过去)"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders?end_date=2000-01-01").json()["data"]
        assert data["total"] == 0

    def test_list_orders_pagination_page_size(self, client):
        """page_size=1 → 第 1 页 1 条, total 不变"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders?page_size=1").json()["data"]
        assert data["total"] >= 3
        assert len(data["items"]) == 1
        assert data["page"] == 1
        assert data["page_size"] == 1

    def test_list_orders_pagination_beyond_last_page(self, client):
        """越页 → 空 items, total/page 回显正确"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders?page=99&page_size=1").json()["data"]
        assert data["items"] == []
        assert data["total"] >= 3
        assert data["page"] == 99

    def test_list_orders_invalid_page_zero(self, client):
        """page=0 → 422 (Query ge=1)"""
        r = client.get("/api/v1/operate/orders?page=0")
        assert r.status_code == 422

    def test_list_orders_invalid_page_size_zero(self, client):
        """page_size=0 → 422 (Query ge=1)"""
        r = client.get("/api/v1/operate/orders?page_size=0")
        assert r.status_code == 422

    def test_list_orders_invalid_page_size_over_max(self, client):
        """page_size=101 → 422 (Query le=100)"""
        r = client.get("/api/v1/operate/orders?page_size=101")
        assert r.status_code == 422

    def test_list_orders_combined_filters(self, client):
        """组合过滤: station_id + status + payment_status 同时生效"""
        _seed_orders(client._sesh)
        data = client.get(
            "/api/v1/operate/orders?station_id=1&status=completed&payment_status=paid"
        ).json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["order_no"] == "ORD001"

    def test_list_orders_requires_auth(self, anon_client):
        """匿名访问 → 401 (router 级 Depends(get_current_user))"""
        r = anon_client.get("/api/v1/operate/orders")
        assert r.status_code == 401


# ════════════════════════════════════════════════════════════
# GET /orders/enterprise — 企业充电订单
# ════════════════════════════════════════════════════════════
class TestEnterpriseOrders:
    """企业维度: user_type 经 cast(String)=='enterprise' 文本比较(SQLite 容忍)。"""

    def test_enterprise_subroute_structure(self, client):
        """现有 UserType 无 enterprise → 空但结构正确"""
        _seed_orders(client._sesh)
        r = client.get("/api/v1/operate/orders/enterprise")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_enterprise_empty_db_not_500(self, client):
        """回归 [35aad373]: 空库查企业订单 → 200 + 空列表(不 500)。

        user_type == 'enterprise' 字面量比较曾在 PG 抛 enum 500; cast(String) 修复后
        端点不抛异常。锁定该修复: 零订单路径不报错。
        """
        r = client.get("/api/v1/operate/orders/enterprise")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_enterprise_pagination(self, client):
        """分页参数回显"""
        r = client.get("/api/v1/operate/orders/enterprise?page=2&page_size=5")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["page"] == 2
        assert data["page_size"] == 5

    def test_enterprise_invalid_page_size(self, client):
        """page_size=0 → 422"""
        r = client.get("/api/v1/operate/orders/enterprise?page_size=0")
        assert r.status_code == 422

    def test_enterprise_requires_auth(self, anon_client):
        """匿名 → 401"""
        assert anon_client.get("/api/v1/operate/orders/enterprise").status_code == 401


# ════════════════════════════════════════════════════════════
# GET /orders/vehicle — 车辆充电订单
# ════════════════════════════════════════════════════════════
class TestVehicleOrders:
    """车辆维度: 按车牌 ilike 过滤; 无 plate 返回全部。"""

    def test_vehicle_filter_by_plate(self, client):
        """按车牌模糊过滤"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders/vehicle?plate_number=京A").json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["plate_number"] == "京A12345"

    def test_vehicle_no_plate_returns_all(self, client):
        """无 plate_number → 返回全部(admin 豁免 team scoping)"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders/vehicle").json()["data"]
        assert data["total"] >= 3

    def test_vehicle_plate_no_match(self, client):
        """车牌无匹配 → 空列表"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders/vehicle?plate_number=ZZZ").json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_vehicle_pagination(self, client):
        """分页生效"""
        _seed_orders(client._sesh)
        data = client.get("/api/v1/operate/orders/vehicle?page_size=2").json()["data"]
        assert len(data["items"]) == 2
        assert data["page_size"] == 2

    def test_vehicle_invalid_page(self, client):
        """page=0 → 422"""
        assert client.get("/api/v1/operate/orders/vehicle?page=0").status_code == 422

    def test_vehicle_requires_auth(self, anon_client):
        """匿名 → 401"""
        assert anon_client.get("/api/v1/operate/orders/vehicle").status_code == 401


# ════════════════════════════════════════════════════════════
# GET /orders/{id} — 订单详情
# ════════════════════════════════════════════════════════════
class TestOrderDetail:
    """订单详情: 5项费用拆解(fees) + fee_items 明细行 + 404 + 鉴权。"""

    def _seed_one(self, client, order_no="D-001"):
        _seed_orders(client._sesh)
        order = client._sesh.query(ChargingOrder).filter(
            ChargingOrder.order_no == order_no
        ).first()
        return order

    def test_detail_basic_fields(self, client):
        """详情基本信息齐全"""
        order = self._seed_one(client, order_no="ORD001")
        r = client.get(f"/api/v1/operate/orders/{order.id}")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["id"] == order.id
        assert d["order_no"] == "ORD001"
        assert d["order_status"] == "completed"
        assert d["payment_status"] == "paid"
        assert d["payment_method"] == "im_b"
        assert d["charged_kwh"] == 50.0

    def test_detail_fees_structure(self, client):
        """fees 含 5项费用 + 3项优惠 + 总额 + 实收"""
        order = self._seed_one(client, order_no="ORD001")
        d = client.get(f"/api/v1/operate/orders/{order.id}").json()["data"]
        fees = d["fees"]
        for key in ("charge_fee", "service_fee", "parking_fee", "occupancy_fee",
                    "reservation_fee", "total_amount", "paid_amount",
                    "discount_amount", "coupon_amount", "points_amount"):
            assert key in fees
        # charge_fee 映射 electricity_fee; seed 未设电费列 → 0
        assert fees["charge_fee"] == 0
        assert fees["total_amount"] == 100.0
        assert fees["paid_amount"] == 100.0

    def test_detail_fee_items(self, client):
        """fee_items 明细行正确序列化"""
        order = self._seed_one(client, order_no="ORD001")
        client._sesh.add(OrderFeeItem(
            order_id=order.id, fee_type=FeeType.ELECTRICITY, fee_name="电费",
            quantity=Decimal("50"), unit_price=Decimal("0.8"),
            amount=Decimal("40.00"), unit="kWh",
        ))
        client._sesh.commit()
        d = client.get(f"/api/v1/operate/orders/{order.id}").json()["data"]
        assert len(d["fee_items"]) == 1
        item = d["fee_items"][0]
        assert item["fee_type"] == "electricity"
        assert item["fee_name"] == "电费"
        assert item["amount"] == 40.0

    def test_detail_no_fee_items(self, client):
        """无 fee_items → 空数组(不报错)"""
        order = self._seed_one(client, order_no="ORD002")
        d = client.get(f"/api/v1/operate/orders/{order.id}").json()["data"]
        assert d["fee_items"] == []

    def test_detail_not_found(self, client):
        """不存在订单 → 404"""
        r = client.get("/api/v1/operate/orders/999999")
        assert r.status_code == 404
        assert r.json()["detail"] == "充电订单不存在"

    def test_detail_requires_auth(self, anon_client):
        """匿名 → 401"""
        assert anon_client.get("/api/v1/operate/orders/1").status_code == 401


# ════════════════════════════════════════════════════════════
# GET /orders/{id}/charge-curve — 订单充电曲线
# ════════════════════════════════════════════════════════════
class TestOrderChargeCurve:
    """充电曲线时间序列: 升序 / 空 / 不存在 / None 字段。"""

    def test_curve_sorted_by_record_time(self, client):
        """有数据: 按 record_time 升序返回, 字段齐全"""
        _seed_curve(client._sesh, order_id=5001)
        r = client.get("/api/v1/operate/orders/5001/charge-curve")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["order_id"] == 5001
        assert data["total"] == 3

        times = [item["record_time"] for item in data["items"]]
        assert times == sorted(times), "曲线点必须按 record_time 升序"
        # 乱序写入后, 升序首点应为 10:00:00 (soc=20)
        assert data["items"][0]["soc"] == 20.0
        assert data["items"][0]["current_power"] == 30.0

        # 字段齐全
        for key in ("record_time", "current_power", "energy_this_minute",
                    "voltage", "current", "soc"):
            assert key in data["items"][0]

    def test_curve_empty_for_existing_order(self, client):
        """边界1 — 订单存在但无曲线数据: 200 + 空 items"""
        _seed_orders(client._sesh)
        order = client._sesh.query(ChargingOrder).first()
        r = client.get(f"/api/v1/operate/orders/{order.id}/charge-curve")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_curve_order_not_exist(self, client):
        """边界2 — admin 不存在的订单: helper 豁免 → 200 + 空 items (admin 平台级)

        非 admin 走 assert_order_team_access 会 404; admin 豁免不抛, 落到空查询。
        与订单列表风格一致(不抛 404)。
        """
        r = client.get("/api/v1/operate/orders/999999/charge-curve")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_curve_null_fields_serialize(self, client):
        """None 字段 → JSON null (不抛 NoneType 错误)"""
        _seed_curve_with_nulls(client._sesh, order_id=5002)
        r = client.get("/api/v1/operate/orders/5002/charge-curve")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        it = items[0]
        assert it["current_power"] is None
        assert it["voltage"] is None
        assert it["soc"] is None
        assert it["record_time"] is not None

    def test_curve_requires_auth(self, anon_client):
        """匿名 → 401"""
        assert anon_client.get("/api/v1/operate/orders/5001/charge-curve").status_code == 401


# ════════════════════════════════════════════════════════════
# team_scope: assert_*_team_access 公共 helper (团队隔离行为)
# 与 test_operate_order_actions.py 同惯例 — 直接断言 helper 语义,
# 覆盖 list 侧 station/enterprise 越权 + detail/curve 的 order 越权。
# ════════════════════════════════════════════════════════════
class TestTeamScoping:
    """团队隔离: 非 admin 仅可见本 team 资源; admin 平台级豁免。

    list/enterprise/vehicle 端点的 team 过滤依赖 is_platform_admin + Station.team_id,
    detail/curve/resolve/retry 经 assert_order_team_access。这些行为由公共 helper
    与 is_platform_admin 决定 —— 直接断言其语义即覆盖 team_scope, 无需 RBAC seed。
    """

    def _seed_scoped(self, session):
        """station(team=100) + 订单挂其上。"""
        session.add(Station(id=1, name="站1", code="ST1", team_id=100))
        session.commit()
        order = ChargingOrder(
            order_no="TS-1", station_id=1, device_id=1, user_id=1,
            user_type=UserType.APP, plate_number="京T0001",
            charged_kwh=Decimal("5"), total_amount=Decimal("10"),
            paid_amount=Decimal("10"), order_status=OrderStatus.COMPLETED,
            payment_status=OrderPaymentStatus.PAID,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order

    # ── assert_order_team_access (detail/curve/resolve/retry) ──
    def test_order_cross_team_denied_404(self, test_db):
        """非 admin 跨团队订单 → 404 (不泄露存在)"""
        session = test_db["session"]
        order = self._seed_scoped(session)
        other = User(id=99, username="other", role=UserRole.OPERATOR,
                     team_id=200, status="active")
        with pytest.raises(HTTPException) as exc:
            assert_order_team_access(session, order.id, other)
        assert exc.value.status_code == 404

    def test_order_same_team_allowed(self, test_db):
        """非 admin 同团队 → 放行(不抛)"""
        session = test_db["session"]
        order = self._seed_scoped(session)
        same = User(id=88, username="same", role=UserRole.OPERATOR,
                    team_id=100, status="active")
        assert_order_team_access(session, order.id, same)  # 不抛即通过

    def test_order_admin_exempt(self, test_db):
        """admin 跨团队 → 放行(平台级)"""
        session = test_db["session"]
        order = self._seed_scoped(session)
        admin = User(id=1, username="admin", role=UserRole.ADMIN,
                     team_id=999, status="active")
        assert_order_team_access(session, order.id, admin)

    def test_order_not_exists_non_admin_404(self, test_db):
        """非 admin 不存在订单 → 404 (helper 查无 team → _team_denied)"""
        session = test_db["session"]
        other = User(id=99, username="other", role=UserRole.OPERATOR,
                     team_id=200, status="active")
        with pytest.raises(HTTPException) as exc:
            assert_order_team_access(session, 999999, other)
        assert exc.value.status_code == 404

    # ── assert_station_team_access (list?station_id 越权) ──
    def test_station_cross_team_denied_404(self, test_db):
        """非 admin 越权 station_id → 404 (list_orders 内调用此 helper)"""
        session = test_db["session"]
        self._seed_scoped(session)  # station 1 team=100
        other = User(id=99, username="other", role=UserRole.OPERATOR,
                     team_id=200, status="active")
        with pytest.raises(HTTPException) as exc:
            assert_station_team_access(session, 1, other)
        assert exc.value.status_code == 404

    def test_station_admin_exempt(self, test_db):
        """admin 越权 station → 放行(返回 Station)"""
        session = test_db["session"]
        self._seed_scoped(session)
        admin = User(id=1, username="admin", role=UserRole.ADMIN,
                     team_id=999, status="active")
        st = assert_station_team_access(session, 1, admin)
        assert st is not None
        assert st.team_id == 100

    # ── assert_enterprise_team_access (enterprise?enterprise_id 越权) ──
    def test_enterprise_cross_team_denied_404(self, test_db):
        """非 admin 越权 enterprise_id → 404 (list_enterprise_orders 内调用)"""
        from app.models.enterprise import Enterprise
        session = test_db["session"]
        session.add(Enterprise(id=1, name="企业A", code="ENT001", owner_team_id=100))
        session.commit()
        other = User(id=99, username="other", role=UserRole.OPERATOR,
                     team_id=200, status="active")
        with pytest.raises(HTTPException) as exc:
            assert_enterprise_team_access(session, 1, other)
        assert exc.value.status_code == 404

    def test_enterprise_not_exists_404(self, test_db):
        """enterprise 不存在 → 404"""
        session = test_db["session"]
        other = User(id=99, username="other", role=UserRole.OPERATOR,
                     team_id=200, status="active")
        with pytest.raises(HTTPException) as exc:
            assert_enterprise_team_access(session, 999999, other)
        assert exc.value.status_code == 404


# ════════════════════════════════════════════════════════════
# 异常兜底: 500 不泄露内部信息
# ════════════════════════════════════════════════════════════
class TestExceptionSafety:
    """端点 except Exception → 500 + 通用 detail('内部错误'), 不泄露堆栈。

    list_orders 首行 try 内即调 is_platform_admin; detail 取到订单后调
    assert_order_team_access —— 两点均在 try 块内, patch 其抛 RuntimeError
    即精确触发兜底分支, 不污染其他模块的 is_platform_admin 引用。
    """

    def test_list_orders_500_generic_detail(self, client, monkeypatch):
        """list_orders 内部异常 → 500 + '内部错误' (不泄露)"""
        import app.api.v1.operate.orders as mod

        def boom(_user):
            raise RuntimeError("DB爆炸敏感信息")

        monkeypatch.setattr(mod, "is_platform_admin", boom)
        r = client.get("/api/v1/operate/orders")
        assert r.status_code == 500
        assert r.json()["detail"] == "内部错误"
        assert "DB爆炸" not in r.text

    def test_detail_500_generic_detail(self, client, monkeypatch):
        """get_order_detail 内部异常 → 500 + '内部错误'"""
        import app.api.v1.operate.orders as mod
        _seed_orders(client._sesh)
        order = client._sesh.query(ChargingOrder).filter(
            ChargingOrder.order_no == "ORD001"
        ).first()

        def boom(*a, **k):
            raise RuntimeError("detail爆炸敏感信息")

        # order 存在 → 越过 404 → 命中 assert_order_team_access (try 内) 触发兜底
        monkeypatch.setattr(mod, "assert_order_team_access", boom)
        r = client.get(f"/api/v1/operate/orders/{order.id}")
        assert r.status_code == 500
        assert r.json()["detail"] == "内部错误"
        assert "detail爆炸" not in r.text

    def test_enterprise_orders_500_generic_detail(self, client, monkeypatch):
        """list_enterprise_orders 内部异常 → 500 + '内部错误'"""
        import app.api.v1.operate.orders as mod

        def boom(_user):
            raise RuntimeError("ent爆炸敏感信息")

        monkeypatch.setattr(mod, "is_platform_admin", boom)
        r = client.get("/api/v1/operate/orders/enterprise")
        assert r.status_code == 500
        assert r.json()["detail"] == "内部错误"
        assert "ent爆炸" not in r.text

    def test_vehicle_orders_500_generic_detail(self, client, monkeypatch):
        """list_vehicle_orders 内部异常 → 500 + '内部错误'"""
        import app.api.v1.operate.orders as mod

        def boom(_user):
            raise RuntimeError("veh爆炸敏感信息")

        monkeypatch.setattr(mod, "is_platform_admin", boom)
        r = client.get("/api/v1/operate/orders/vehicle")
        assert r.status_code == 500
        assert r.json()["detail"] == "内部错误"
        assert "veh爆炸" not in r.text

    def test_curve_500_generic_detail(self, client, monkeypatch):
        """get_order_charge_curve 内部异常 → 500 + '内部错误'"""
        import app.api.v1.operate.orders as mod

        def boom(*a, **k):
            raise RuntimeError("curve爆炸敏感信息")

        monkeypatch.setattr(mod, "assert_order_team_access", boom)
        r = client.get("/api/v1/operate/orders/5001/charge-curve")
        assert r.status_code == 500
        assert r.json()["detail"] == "内部错误"
        assert "curve爆炸" not in r.text


# ════════════════════════════════════════════════════════════
# 真实端点 team scoping: 非 admin 用户经真实登录链 → list/enterprise/vehicle
# 仅返回本 team 订单, 越权 station_id → 404。覆盖端点内 if not is_platform_admin
# 的 join(Station)+filter(Station.team_id) 分支与 assert_station_team_access 调用。
# ════════════════════════════════════════════════════════════
class TestRealEndpointTeamScoping:
    """登录非 admin(ENGINEER, team=100) 用户, 验证只读端点的 team 过滤生效。"""

    def _seed_team_world(self, client):
        """team100(本) + team200(他) 各一站点一订单; 返回 ENGINEER token + 跨 team 资源。"""
        import bcrypt
        from app.models.user import Team
        from tests.conftest import _get_token

        s = client._sesh
        t100 = Team(name="本团队", code="TM100")
        t200 = Team(name="他团队", code="TM200")
        s.add_all([t100, t200]); s.commit(); s.refresh(t100); s.refresh(t200)

        pwd = "eng123456"
        eng = User(
            username="eng_team100", real_name="本团队工程师", role=UserRole.ENGINEER,
            team_id=t100.id, status="active",
            password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
        )
        s.add(eng); s.commit()

        s.add_all([
            Station(id=10, name="本站", code="ST10", team_id=t100.id),
            Station(id=20, name="他站", code="ST20", team_id=t200.id),
        ])
        s.add_all([
            ChargingOrder(order_no="MINE01", station_id=10, device_id=1, user_id=1,
                user_type=UserType.APP, plate_number="京MINE1", charged_kwh="10",
                total_amount="20", paid_amount="20", order_status=OrderStatus.COMPLETED,
                payment_status=OrderPaymentStatus.PAID),
            ChargingOrder(order_no="OTHER02", station_id=20, device_id=2, user_id=2,
                user_type=UserType.APP, plate_number="京OTH02", charged_kwh="10",
                total_amount="20", paid_amount="20", order_status=OrderStatus.COMPLETED,
                payment_status=OrderPaymentStatus.PAID),
        ])
        s.commit()
        token = _get_token(client, "eng_team100", pwd)
        return token, t200.id

    def test_list_only_own_team_orders(self, client):
        """非 admin list → 仅本 team 订单, 不见他团队"""
        token, _ = self._seed_team_world(client)
        h = {"Authorization": f"Bearer {token}"}
        data = client.get("/api/v1/operate/orders", headers=h).json()["data"]
        nos = [it["order_no"] for it in data["items"]]
        assert "MINE01" in nos
        assert "OTHER02" not in nos

    def test_list_cross_station_404(self, client):
        """非 admin list?station_id=他团队站 → 404 (不泄露存在)"""
        token, _ = self._seed_team_world(client)
        h = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/v1/operate/orders?station_id=20", headers=h)
        assert r.status_code == 404

    def test_list_own_station_ok(self, client):
        """非 admin list?station_id=本团队站 → 200, 仅本订单"""
        token, _ = self._seed_team_world(client)
        h = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/v1/operate/orders?station_id=10", headers=h)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["order_no"] == "MINE01"

    def test_vehicle_only_own_team_orders(self, client):
        """非 admin vehicle → 仅本 team 订单"""
        token, _ = self._seed_team_world(client)
        h = {"Authorization": f"Bearer {token}"}
        data = client.get("/api/v1/operate/orders/vehicle", headers=h).json()["data"]
        nos = [it["order_no"] for it in data["items"]]
        assert "MINE01" in nos
        assert "OTHER02" not in nos

    def test_enterprise_only_own_team(self, client):
        """非 admin enterprise → 仅本 team (seed 无 enterprise 订单 → 空, 但走 team join 不 500)"""
        token, _ = self._seed_team_world(client)
        h = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/v1/operate/orders/enterprise", headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

