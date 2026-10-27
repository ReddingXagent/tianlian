"""运营订单查询/异常闭环 API 测试 (工作卡 fe57636f)

覆盖 app/api/v1/operate/orders.py (挂 /api/v1/operate 前缀):
- GET  /operate/orders                          订单列表 (admin 全量 / 非 admin 按 team 过滤)
- GET  /operate/orders/enterprise               企业充电订单 (user_type=enterprise)
- GET  /operate/orders/vehicle                  车辆充电订单 (按车牌)
- GET  /operate/orders/{id}/charge-curve        订单充电曲线 (无数据 → 空 items 非 404)
- GET  /operate/orders/{id}                     订单详情 (5项费用拆解 + fee_items)
- POST /operate/orders/{id}/resolve             标记异常订单已处理 (charging:manage)
- POST /operate/orders/{id}/retry-charge        重试计费 (仅 FAILED; charging:manage)

team scoping (任务卡 ab5c5f17): 非 admin 仅可见/操作本 team 订单 (order.station_id→team),
越权/不存在 → 404 (不泄露存在)。
认证: router 级 get_current_user; resolve/retry-charge 额外 require_write_permission("charging:manage"),
viewer 无此权限 → 403 (即使 body 非法也先 403, 路由级依赖在 body 解析前执行)。
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import bcrypt

from app.models.charging_order import (
    ChargingOrder,
    OrderStatus,
    OrderPaymentStatus,
    PaymentMethod,
    UserType,
)
from app.models.device_qrcode import DeviceQRCode  # noqa: F401  (确保模型注册)
from app.models.spec_tables import OrderChargeCurve
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

ORD_URL = "/api/v1/operate/orders"


# ─── helpers ───

def _add_user(session, username, *, role=UserRole.VIEWER, team_id=None, password="pw123456"):
    u = User(
        username=username,
        real_name=username,
        role=role,
        team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_station(session, *, team_id=None, tag=""):
    st = Station(
        name=f"订单站{tag}{uuid.uuid4().hex[:4]}",
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址",
        status=StationStatus.NORMAL,
        team_id=team_id,
    )
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _seed_order(
    session,
    *,
    station_id,
    order_no=None,
    order_status=OrderStatus.COMPLETED,
    payment_status=OrderPaymentStatus.PAID,
    user_type=UserType.APP,
    plate_number=None,
    charged_kwh=Decimal("10.0"),
    total_amount=Decimal("20.00"),
    paid_amount=Decimal("20.00"),
    electricity_fee=Decimal("12.00"),
    service_fee=Decimal("8.00"),
    device_id=1,
    user_id=None,
    payment_method=PaymentMethod.WECHAT,
):
    o = ChargingOrder(
        order_no=order_no or f"ord_{uuid.uuid4().hex[:12]}",
        station_id=station_id,
        device_id=device_id,
        user_id=user_id,
        user_type=user_type,
        plate_number=plate_number,
        charged_kwh=charged_kwh,
        total_amount=total_amount,
        paid_amount=paid_amount,
        electricity_fee=electricity_fee,
        service_fee=service_fee,
        order_status=order_status,
        payment_status=payment_status,
        payment_method=payment_method,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


# ==================== 1. 订单列表 ====================

class TestListOrders:
    """GET /operate/orders —— admin 全量; team scoping; 过滤; 分页。"""

    def test_admin_list_returns_items(self, client):
        s = client._sesh
        st = _seed_station(s, tag="L1")
        o = _seed_order(s, station_id=st.id, plate_number="京A12345")
        r = client.get(ORD_URL)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] >= 1
        assert any(it["id"] == o.id for it in data["items"])

    def test_filter_by_status_and_payment(self, client):
        s = client._sesh
        st = _seed_station(s, tag="L2")
        _seed_order(s, station_id=st.id, order_status=OrderStatus.COMPLETED,
                    payment_status=OrderPaymentStatus.PAID)
        _seed_order(s, station_id=st.id, order_status=OrderStatus.PENDING,
                    payment_status=OrderPaymentStatus.UNPAID)
        r = client.get(ORD_URL, params={"status": "completed", "payment_status": "paid"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert items
        assert all(it["order_status"] == "completed" for it in items)
        assert all(it["payment_status"] == "paid" for it in items)

    def test_keyword_search_by_order_no(self, client):
        s = client._sesh
        st = _seed_station(s, tag="L3")
        o = _seed_order(s, station_id=st.id, order_no="ord_KEYWORD_HIT_99")
        r = client.get(ORD_URL, params={"keyword": "KEYWORD_HIT"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert any(it["id"] == o.id for it in items)

    def test_team_scoping_non_admin_only_own_team(self, client):
        """非 admin 仅返回本 team 站点的订单。"""
        from app.models.user import Team
        s = client._sesh
        t_mine = Team(name=f"队我{uuid.uuid4().hex[:4]}", code=f"TM{uuid.uuid4().hex[:4]}")
        t_other = Team(name=f"队他{uuid.uuid4().hex[:4]}", code=f"TO{uuid.uuid4().hex[:4]}")
        s.add_all([t_mine, t_other])
        s.commit()
        s.refresh(t_mine); s.refresh(t_other)

        st_mine = _seed_station(s, team_id=t_mine.id, tag="mine")
        st_other = _seed_station(s, team_id=t_other.id, tag="other")
        o_mine = _seed_order(s, station_id=st_mine.id)
        o_other = _seed_order(s, station_id=st_other.id)

        u = _add_user(s, f"viewer_{uuid.uuid4().hex[:6]}", role=UserRole.VIEWER, team_id=t_mine.id)
        tok = _login_token(client, u.username)
        r = client.get(ORD_URL, headers=_auth(tok))
        assert r.status_code == 200
        ids = [it["id"] for it in r.json()["data"]["items"]]
        assert o_mine.id in ids
        assert o_other.id not in ids  # 跨 team 不可见

    def test_non_admin_cross_team_station_404(self, client):
        """非 admin 按他人 station_id 过滤 → 404 (不泄露存在)。"""
        from app.models.user import Team
        s = client._sesh
        t_other = Team(name=f"队他{uuid.uuid4().hex[:4]}", code=f"TO{uuid.uuid4().hex[:4]}")
        s.add(t_other); s.commit(); s.refresh(t_other)
        st_other = _seed_station(s, team_id=t_other.id, tag="x")

        t_mine = Team(name=f"队我{uuid.uuid4().hex[:4]}", code=f"TM{uuid.uuid4().hex[:4]}")
        s.add(t_mine); s.commit(); s.refresh(t_mine)
        u = _add_user(s, f"viewer_{uuid.uuid4().hex[:6]}", role=UserRole.VIEWER, team_id=t_mine.id)
        tok = _login_token(client, u.username)
        r = client.get(ORD_URL, params={"station_id": st_other.id}, headers=_auth(tok))
        assert r.status_code == 404

    def test_page_size_le_100_validated(self, client):
        r = client.get(ORD_URL, params={"page_size": 101})
        assert r.status_code == 422  # Query(le=100)

    def test_anonymous_401(self, anon_client):
        r = anon_client.get(ORD_URL)
        assert r.status_code == 401


# ==================== 2. 企业 / 车辆订单 ====================

class TestEnterpriseAndVehicleOrders:

    def test_enterprise_orders_empty_when_only_app_card(self, client):
        """无 ENTERPRISE 支付订单 → 端点返回空列表, 不报错 (正常路径 + team scoping 不误伤)。

        企业订单以 payment_method=ENTERPRISE 标识 (卡 6c7e252c); 默认IM-B支付订单不进列表。
        """
        s = client._sesh
        st = _seed_station(s, tag="E1")
        _seed_order(s, station_id=st.id, user_type=UserType.APP, user_id=9001)
        r = client.get("/api/v1/operate/orders/enterprise")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["items"] == []  # 无 ENTERPRISE 支付订单
        assert d["total"] == 0

    def test_enterprise_filter_by_payment_method_semantics(self, client):
        """企业订单按 payment_method=ENTERPRISE 过滤 (卡 6c7e252c 回归)。

        历史缺陷: list_enterprise_orders 误用 user_type=='enterprise' 过滤, 但
        UserType 枚举仅 app/card, 'enterprise' 非其合法值 —— 脏数据写入该列会令
        SAEnum 反序列化抛 LookupError → 500。修复后改用 payment_method=ENTERPRISE:
        真正标识"企业订单"的是支付方式(企业挂账)而非用户身份载体。

        本测试钉死正确语义: ENTERPRISE 支付的订单进列表, WECHAT 支付的不进,
        且不再因 user_type 脏数据 500。
        """
        s = client._sesh
        st = _seed_station(s, tag="E1ent")
        ent_order = _seed_order(
            s, station_id=st.id, user_id=9001,
            payment_method=PaymentMethod.ENTERPRISE,
        )
        # 对照: 同站点IM-B支付订单不应出现在企业订单列表
        im_b_order = _seed_order(
            s, station_id=st.id, user_id=9002,
            payment_method=PaymentMethod.WECHAT,
        )

        r = client.get("/api/v1/operate/orders/enterprise")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        ids = [it["id"] for it in data["items"]]
        assert ent_order.id in ids                  # ENTERPRISE 支付进列表
        assert im_b_order.id not in ids           # WECHAT 支付不进列表
        assert data["total"] >= 1

    def test_vehicle_orders_by_plate(self, client):
        s = client._sesh
        st = _seed_station(s, tag="V1")
        target = _seed_order(s, station_id=st.id, plate_number="沪B88888")
        _seed_order(s, station_id=st.id, plate_number="沪B99999")
        r = client.get("/api/v1/operate/orders/vehicle", params={"plate_number": "88888"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["id"] == target.id


# ==================== 3. 充电曲线 / 详情 ====================

class TestChargeCurveAndDetail:

    def test_charge_curve_empty_when_no_data(self, client):
        """订单无曲线数据 → 空 items (非 404)。"""
        s = client._sesh
        st = _seed_station(s, tag="C1")
        o = _seed_order(s, station_id=st.id)
        r = client.get(f"{ORD_URL}/{o.id}/charge-curve")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["items"] == []
        assert d["total"] == 0

    def test_charge_curve_returns_time_series(self, client):
        s = client._sesh
        st = _seed_station(s, tag="C2")
        o = _seed_order(s, station_id=st.id)
        base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(3):
            s.add(OrderChargeCurve(
                order_id=o.id, record_time=base.replace(minute=i),
                current_power=10.0 + i, voltage=400.0, current=30.0, soc=50.0 + i,
            ))
        s.commit()
        r = client.get(f"{ORD_URL}/{o.id}/charge-curve")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 3
        assert items[0]["current_power"] == 10.0  # 按 record_time 升序

    def test_charge_curve_cross_team_404(self, client):
        from app.models.user import Team
        s = client._sesh
        t_other = Team(name=f"队他{uuid.uuid4().hex[:4]}", code=f"TO{uuid.uuid4().hex[:4]}")
        t_mine = Team(name=f"队我{uuid.uuid4().hex[:4]}", code=f"TM{uuid.uuid4().hex[:4]}")
        s.add_all([t_other, t_mine]); s.commit(); s.refresh(t_other); s.refresh(t_mine)
        st_other = _seed_station(s, team_id=t_other.id, tag="x")
        o = _seed_order(s, station_id=st_other.id)
        u = _add_user(s, f"viewer_{uuid.uuid4().hex[:6]}", role=UserRole.VIEWER, team_id=t_mine.id)
        tok = _login_token(client, u.username)
        r = client.get(f"{ORD_URL}/{o.id}/charge-curve", headers=_auth(tok))
        assert r.status_code == 404

    def test_order_detail_has_fees_breakdown(self, client):
        s = client._sesh
        st = _seed_station(s, tag="D1")
        o = _seed_order(s, station_id=st.id, electricity_fee=Decimal("12.00"),
                        service_fee=Decimal("8.00"), total_amount=Decimal("20.00"),
                        paid_amount=Decimal("20.00"))
        r = client.get(f"{ORD_URL}/{o.id}")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["id"] == o.id
        fees = d["fees"]
        assert fees["charge_fee"] == 12.0
        assert fees["service_fee"] == 8.0
        assert fees["total_amount"] == 20.0
        assert "fee_items" in d

    def test_order_detail_not_exist_404(self, client):
        r = client.get(f"{ORD_URL}/999999")
        assert r.status_code == 404


# ==================== 4. 异常订单闭环 ====================

class TestResolveAbnormalOrder:
    """POST /operate/orders/{id}/resolve —— charging:manage; 幂等覆盖。"""

    def test_resolve_ok_and_idempotent(self, client):
        s = client._sesh
        st = _seed_station(s, tag="R1")
        o = _seed_order(s, station_id=st.id, order_status=OrderStatus.FAILED)
        body = {"handle_type": "refunded", "remark": "已退款"}
        r = client.post(f"{ORD_URL}/{o.id}/resolve", json=body)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["abnormal_handle_type"] == "refunded"
        assert d["abnormal_handle_remark"] == "已退款"
        assert d["abnormal_handled_by"] is not None

        # 幂等: 再次 resolve 覆盖, 不报错
        body2 = {"handle_type": "false_alarm", "remark": "误报"}
        r2 = client.post(f"{ORD_URL}/{o.id}/resolve", json=body2)
        assert r2.status_code == 200
        assert r2.json()["data"]["abnormal_handle_type"] == "false_alarm"

    def test_resolve_invalid_handle_type_422(self, client):
        s = client._sesh
        st = _seed_station(s, tag="R2")
        o = _seed_order(s, station_id=st.id)
        r = client.post(f"{ORD_URL}/{o.id}/resolve", json={"handle_type": "bogus"})
        assert r.status_code == 422  # Literal 约束

    def test_resolve_not_exist_404(self, client):
        r = client.post(f"{ORD_URL}/999999/resolve", json={"handle_type": "written_off"})
        assert r.status_code == 404

    def test_resolve_viewer_forbidden_403(self, client):
        """viewer 无 charging:manage → 403 (body 非法也不掩盖, 路由级依赖先执行)。"""
        from app.models.user import Team
        s = client._sesh
        t = Team(name=f"队{uuid.uuid4().hex[:4]}", code=f"T{uuid.uuid4().hex[:4]}")
        s.add(t); s.commit(); s.refresh(t)
        st = _seed_station(s, team_id=t.id, tag="R3")
        o = _seed_order(s, station_id=st.id)
        u = _add_user(s, f"viewer_{uuid.uuid4().hex[:6]}", role=UserRole.VIEWER, team_id=t.id)
        tok = _login_token(client, u.username)
        r = client.post(f"{ORD_URL}/{o.id}/resolve", json={"handle_type": "refunded"}, headers=_auth(tok))
        assert r.status_code == 403

    def test_resolve_cross_team_404(self, client):
        from app.models.user import Team
        s = client._sesh
        t_other = Team(name=f"队他{uuid.uuid4().hex[:4]}", code=f"TO{uuid.uuid4().hex[:4]}")
        t_mine = Team(name=f"队我{uuid.uuid4().hex[:4]}", code=f"TM{uuid.uuid4().hex[:4]}")
        s.add_all([t_other, t_mine]); s.commit(); s.refresh(t_other); s.refresh(t_mine)
        st_other = _seed_station(s, team_id=t_other.id, tag="x")
        o = _seed_order(s, station_id=st_other.id)
        # operator 持 charging:manage, 但跨 team → 404 (先过 team 校验)
        u = _add_user(s, f"oper_{uuid.uuid4().hex[:6]}", role=UserRole.OPERATOR, team_id=t_mine.id)
        tok = _login_token(client, u.username)
        r = client.post(f"{ORD_URL}/{o.id}/resolve", json={"handle_type": "refunded"}, headers=_auth(tok))
        assert r.status_code == 404

    def test_resolve_anonymous_401(self, anon_client):
        r = anon_client.post(f"{ORD_URL}/1/resolve", json={"handle_type": "refunded"})
        assert r.status_code == 401


# ==================== 5. 重试计费 ====================

class TestRetryCharge:

    def test_retry_non_failed_409(self, client):
        """非 FAILED 订单重试 → 409。"""
        s = client._sesh
        st = _seed_station(s, tag="RT1")
        o = _seed_order(s, station_id=st.id, order_status=OrderStatus.COMPLETED)
        r = client.post(f"{ORD_URL}/{o.id}/retry-charge")
        assert r.status_code == 409
        assert "failed" in r.json()["detail"]

    def test_retry_not_exist_404(self, client):
        r = client.post(f"{ORD_URL}/999999/retry-charge")
        assert r.status_code == 404

    def test_retry_viewer_forbidden_403(self, client):
        from app.models.user import Team
        s = client._sesh
        t = Team(name=f"队{uuid.uuid4().hex[:4]}", code=f"T{uuid.uuid4().hex[:4]}")
        s.add(t); s.commit(); s.refresh(t)
        st = _seed_station(s, team_id=t.id, tag="RT2")
        o = _seed_order(s, station_id=st.id, order_status=OrderStatus.FAILED)
        u = _add_user(s, f"viewer_{uuid.uuid4().hex[:6]}", role=UserRole.VIEWER, team_id=t.id)
        tok = _login_token(client, u.username)
        r = client.post(f"{ORD_URL}/{o.id}/retry-charge", headers=_auth(tok))
        assert r.status_code == 403

    def test_retry_failed_settles_ok(self, client):
        """FAILED 订单重试计费 → 200, 返回费用结构 (兜底默认费率, 不抛异常)。"""
        s = client._sesh
        st = _seed_station(s, tag="RT3")
        o = _seed_order(
            s, station_id=st.id, order_status=OrderStatus.FAILED,
            charged_kwh=Decimal("5.0"),
        )
        r = client.post(f"{ORD_URL}/{o.id}/retry-charge")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["order_id"] == o.id
        # 关键字段齐备
        for k in ("energy_fee", "service_fee", "total_amount", "used_default"):
            assert k in d


# ==================== 6. 覆盖率提升补遗 (卡 9de1bf44) ====================
# 现有测试已达 91%; 下列端点分支此前未覆盖:
# - enterprise?enterprise_id= 过滤分支 (admin 过滤 / 非 admin 越权 404 走 HTTPException 穿透)
# - resolve 异常兜底 except Exception
# - retry-charge settle 返回 {error:...} → 500
# - retry-charge 异常兜底 except Exception

class TestEnterpriseIdFilter:
    """GET /orders/enterprise?enterprise_id= — 端点内 enterprise_id 过滤分支 (133-135)
    与 helper 抛 HTTPException 后穿透 (158 行 except HTTPException: raise)。

    enterprise_id 在端点里映射到 ChargingOrder.user_id (企业挂账订单的 user_id 即企业)。
    TestTeamScoping 仅断言 helper 语义; 本类走真实端点覆盖端内分支 + 404 穿透。
    """

    def _seed_enterprise_world(self, client):
        """两企业分属不同 team, 本 team 挂一笔 ENTERPRISE 支付订单 (user_id=企业id)。"""
        from app.models.enterprise import Enterprise
        from app.models.user import Team

        s = client._sesh
        t100 = Team(name=f"企业本{uuid.uuid4().hex[:4]}", code=f"ET{uuid.uuid4().hex[:4]}")
        t200 = Team(name=f"企业他{uuid.uuid4().hex[:4]}", code=f"EF{uuid.uuid4().hex[:4]}")
        s.add_all([t100, t200]); s.commit(); s.refresh(t100); s.refresh(t200)

        ent_mine = Enterprise(id=301, name="本企业", code="ENT301", owner_team_id=t100.id)
        ent_other = Enterprise(id=302, name="他企业", code="ENT302", owner_team_id=t200.id)
        s.add_all([ent_mine, ent_other]); s.commit()

        st = _seed_station(s, team_id=t100.id, tag="EF1")
        _seed_order(s, station_id=st.id, user_id=301,
                    payment_method=PaymentMethod.ENTERPRISE, plate_number="企A301")
        return t100, t200, ent_other

    def test_admin_filter_by_enterprise_id(self, client):
        """admin 传 enterprise_id → 仅返回该企业的 ENTERPRISE 订单 (走 filter(user_id==))。"""
        self._seed_enterprise_world(client)
        # 默认 client = admin, 豁免 team scoping 与企业归属校验
        data = client.get("/api/v1/operate/orders/enterprise?enterprise_id=301").json()["data"]
        assert data["total"] == 1
        assert all(it["id"] is not None for it in data["items"])

    def test_non_admin_cross_enterprise_404(self, client):
        """非 admin 越权 enterprise_id → assert_enterprise_team_access 抛 404, 经端点
        except HTTPException: raise (158 行) 原样穿透, 不被 500 兜底吞掉。"""
        t100, t200, ent_other = self._seed_enterprise_world(client)
        s = client._sesh
        # 本团队用户(t100) 查他团队企业(ent_other, 属 t200) → 404
        u = _add_user(s, f"viewer_{uuid.uuid4().hex[:6]}", role=UserRole.OPERATOR, team_id=t100.id)
        tok = _login_token(client, u.username)
        r = client.get(
            f"/api/v1/operate/orders/enterprise?enterprise_id={ent_other.id}",
            headers=_auth(tok),
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "企业不存在"

    def test_non_admin_own_enterprise_ok(self, client):
        """非 admin 传本团队企业 id → 放行, 返回该企业订单 (134 行不抛, 走 filter)。"""
        t100, _, _ = self._seed_enterprise_world(client)
        s = client._sesh
        u = _add_user(s, f"oper_{uuid.uuid4().hex[:6]}", role=UserRole.OPERATOR, team_id=t100.id)
        tok = _login_token(client, u.username)
        r = client.get(
            "/api/v1/operate/orders/enterprise?enterprise_id=301",
            headers=_auth(tok),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] == 1


class TestResolveExceptionSafety:
    """POST /orders/{id}/resolve except Exception 兜底 (368-371)。

    assert_order_team_access 在 try 内, patch 其抛 RuntimeError → 触发兜底 500。
    """

    def test_resolve_500_generic_detail(self, client, monkeypatch):
        import app.api.v1.operate.orders as mod
        s = client._sesh
        st = _seed_station(s, tag="RE1")
        o = _seed_order(s, station_id=st.id, order_status=OrderStatus.FAILED)

        def boom(*a, **k):
            raise RuntimeError("resolve爆炸敏感信息")

        monkeypatch.setattr(mod, "assert_order_team_access", boom)
        r = client.post(f"{ORD_URL}/{o.id}/resolve",
                        json={"handle_type": "refunded"})
        assert r.status_code == 500
        assert r.json()["detail"] == "内部错误"
        assert "resolve爆炸" not in r.text


class TestRetryChargeErrorBranch:
    """retry-charge 两条未覆盖分支:
    - settle_charging_session 返回 {error:...} dict → 500 (416-417)
    - settle_charging_session 抛异常 → 兜底 500 (433-436)
    """

    def test_retry_settle_error_returns_500(self, client, monkeypatch):
        """settle 内部失败返回 {error:...} → 端点 500 '重试计费失败'。"""
        import app.api.v1.operate.orders as mod
        s = client._sesh
        st = _seed_station(s, tag="RTE1")
        o = _seed_order(s, station_id=st.id, order_status=OrderStatus.FAILED,
                        charged_kwh=Decimal("5.0"))

        monkeypatch.setattr(mod, "settle_charging_session",
                            lambda *a, **k: {"error": "charging_session settle failed"})
        r = client.post(f"{ORD_URL}/{o.id}/retry-charge")
        assert r.status_code == 500
        assert r.json()["detail"] == "重试计费失败, 请稍后重试"

    def test_retry_exception_500_generic_detail(self, client, monkeypatch):
        """settle_charging_session 抛 RuntimeError → 兜底 500 '内部错误' (不泄露)。"""
        import app.api.v1.operate.orders as mod
        s = client._sesh
        st = _seed_station(s, tag="RTE2")
        o = _seed_order(s, station_id=st.id, order_status=OrderStatus.FAILED,
                        charged_kwh=Decimal("5.0"))

        def boom(*a, **k):
            raise RuntimeError("retry结算爆炸敏感信息")

        monkeypatch.setattr(mod, "settle_charging_session", boom)
        r = client.post(f"{ORD_URL}/{o.id}/retry-charge")
        assert r.status_code == 500
        assert r.json()["detail"] == "内部错误"
        assert "retry结算爆炸" not in r.text


# ==================== 7. retry-charge team scoping 真实端点 (卡 1a810c16) ====================

class TestRetryChargeTeamScoping:
    """POST /orders/{id}/retry-charge 跨 team → 404 (真实端点, 非仅 helper 断言)。

    TestAbnormalOrderTeamScope (tests/test_operate_order_actions.py) 仅直接断言
    assert_order_team_access helper 语义; resolve 跨队已在 TestResolveAbnormalOrder
    覆盖, retry-charge 的端点级 404 穿透此前未测。
    """

    def test_retry_cross_team_404(self, client):
        from app.models.user import Team
        s = client._sesh
        t_other = Team(name=f"队他{uuid.uuid4().hex[:4]}", code=f"TR{uuid.uuid4().hex[:4]}")
        t_mine = Team(name=f"队我{uuid.uuid4().hex[:4]}", code=f"TM{uuid.uuid4().hex[:4]}")
        s.add_all([t_other, t_mine]); s.commit(); s.refresh(t_other); s.refresh(t_mine)
        st_other = _seed_station(s, team_id=t_other.id, tag="rtc")
        o = _seed_order(s, station_id=st_other.id, order_status=OrderStatus.FAILED)
        # operator 持 charging:manage (过权限门), 但订单属他队 → 404 (team 校验先于状态机)
        u = _add_user(s, f"oper_{uuid.uuid4().hex[:6]}", role=UserRole.OPERATOR, team_id=t_mine.id)
        tok = _login_token(client, u.username)
        r = client.post(f"{ORD_URL}/{o.id}/retry-charge", headers=_auth(tok))
        assert r.status_code == 404

    def test_retry_same_team_allowed_past_team_gate(self, client):
        """同 team operator 持 charging:manage → 过 team 校验, 进入状态机 (FAILED → 200)。"""
        from app.models.user import Team
        s = client._sesh
        t = Team(name=f"队同{uuid.uuid4().hex[:4]}", code=f"TS{uuid.uuid4().hex[:4]}")
        s.add(t); s.commit(); s.refresh(t)
        st = _seed_station(s, team_id=t.id, tag="rts")
        o = _seed_order(s, station_id=st.id, order_status=OrderStatus.FAILED,
                        charged_kwh=Decimal("5.0"))
        u = _add_user(s, f"oper_{uuid.uuid4().hex[:6]}", role=UserRole.OPERATOR, team_id=t.id)
        tok = _login_token(client, u.username)
        r = client.post(f"{ORD_URL}/{o.id}/retry-charge", headers=_auth(tok))
        assert r.status_code == 200, r.text
