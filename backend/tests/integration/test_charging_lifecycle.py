"""充电生命周期 E2E 集成测试 (用户端云端契约 §7 + §5, 工作卡 e323153a)

跨端点全链路串联, 验证模块间协作而非单点行为 (单点已由 tests/api/test_business_orders.py 覆盖)。

覆盖链路:
- happy path : 建单 → 状态推进 → 停止 → 完整明细 (§7.1/§7.2/§7.3/§7.7, kwh/fee/duration)
- 取消流程   : 建单 → 取消 → 同 connector 可重下 (§7.5)
- 互斥       : 已有活跃订单的 connector 再建 → 业务错误 (§7.1 CONNECTOR_BUSY)
- 跨模块     : 充电完成 → 提交开票申请 → 查开票列表 (§7 + §5)
- 权限隔离   : 用户 A 的订单用户 B 不可见/不可操作 → 404

金额: 响应里是分(整数); 模型存储是元(Decimal)。
认证: C 端用户 token (get_current_user), 用 VIEWER 模拟。
"""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import bcrypt
import pytest
from fastapi import HTTPException

from app.api.v1 import business_orders
from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
    PaymentMethod,
    UserType,
)
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

ORDERS = "/api/v1/business/orders"
INVOICES = "/api/v1/business/invoices"


# ─── helpers (复用 test_business_orders.py 的 fixture 风格) ───

def _add_user(session, username, role=UserRole.VIEWER, password="pw123456"):
    u = User(
        username=username,
        real_name=username,
        role=role,
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


def _seed_station(session, *, name="甘天地光储充示范站"):
    from app.models.user import Team

    # 卡 71062d84: 开票申请要求订单场站挂 team (无 team 的申请对所有团队
    # 运营不可见, apply 已拒绝 team 缺失), 故种子站显式建团队归属。
    team = Team(name=f"团队{uuid.uuid4().hex[:6]}", code=f"TM{uuid.uuid4().hex[:6].upper()}")
    session.add(team)
    session.commit()
    session.refresh(team)
    st = Station(
        name=name,
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址",
        status=StationStatus.NORMAL,
        team_id=team.id,
    )
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _seed_device(session, *, station_id, status=DeviceStatus.ONLINE):
    dev = Device(
        sn=f"SN{uuid.uuid4().hex[:10]}",
        name="充电桩",
        code=f"CHG{uuid.uuid4().hex[:6].upper()}",
        type=DeviceType.CHARGER_DC,
        status=status,
        station_id=station_id,
        rated_power=120.0,
        gun_count=2,
    )
    session.add(dev)
    session.commit()
    session.refresh(dev)
    return dev


@pytest.fixture
def c_user(client):
    """C 端用户 (VIEWER) + 登录 token。"""
    u = _add_user(client._sesh, f"appuser_{uuid.uuid4().hex[:6]}")
    token = _login_token(client, u.username)
    return u, token


@pytest.fixture
def station_and_device(client):
    st = _seed_station(client._sesh)
    dev = _seed_device(client._sesh, station_id=st.id)
    return st, dev


def _create_order(client, token, station_id, device_id, connector_id=1):
    """通过 API 建单, 返回 data dict。"""
    r = client.post(
        ORDERS,
        json={"station_id": station_id, "device_id": device_id, "connector_id": connector_id},
        headers=_auth(token),
    )
    assert r.status_code == 201, f"建单失败: {r.text[:300]}"
    assert r.json()["code"] == 0
    return r.json()["data"]


# =====================================================================
# 链路1: happy path — 建单 → 状态 → 停止 → 明细
# =====================================================================

class TestHappyPath:
    def test_full_lifecycle(self, client, c_user, station_and_device):
        """§7.1→§7.3→§7.2→§7.7 全链路: 验证 kwh/fee/duration 字段流转正确。

        真实充电桩会把 pending 推进到 charging (OCPP StartTransaction 回调);
        此处无桩, 建单后手动推进到 charging 再停止, 聚焦端到端字段一致性。
        """
        u, token = c_user
        st, dev = station_and_device

        # §7.1 建单 → pending
        created = _create_order(client, token, st.id, dev.id, connector_id=1)
        order_no = created["order_id"]
        assert created["order_status"] == "pending"

        # 模拟桩端 StartTransaction 回调: pending → charging + 写入实时遥测
        s = client._sesh
        order = s.query(ChargingOrder).filter(ChargingOrder.order_no == order_no).one()
        order.order_status = OrderStatus.CHARGING
        order.start_time = datetime.now(timezone.utc) - timedelta(minutes=45)
        order.charged_kwh = Decimal("23.50")
        order.start_soc = Decimal("35.0")
        order.end_soc = Decimal("100.0")
        s.commit()

        # §7.3 实时状态: charging 期间查得到 kwh/soc/power
        r = client.get(f"{ORDERS}/{order_no}/status", headers=_auth(token))
        assert r.status_code == 200, r.text
        status = r.json()["data"]
        assert status["order_status"] == "charging"
        assert status["charged_kwh"] == 23.50
        assert status["start_soc"] == 35.0

        # §7.2 停止: charging → completed
        r = client.post(f"{ORDERS}/{order_no}/stop", headers=_auth(token))
        assert r.status_code == 200, r.text
        stopped = r.json()["data"]
        assert stopped["order_status"] == "completed"
        assert stopped["charged_kwh"] == 23.50
        assert stopped["duration_minutes"] >= 0
        assert stopped["total_amount"] >= 0
        assert stopped["stop_reason"] == "user_manual"

        # §7.7 完整明细: 状态/费用字段齐全
        r = client.get(f"{ORDERS}/{order_no}?detail=full", headers=_auth(token))
        assert r.status_code == 200, r.text
        detail = r.json()["data"]
        assert detail["order_id"] == order_no
        assert detail["order_status"] == "completed"
        assert detail["charged_kwh"] == 23.50
        # 费用字段存在且为分(整数); start/end_time 已落
        assert "electricity_fee" in detail
        assert "total_amount" in detail
        assert detail["start_time"]
        assert detail["end_time"]
        assert detail["duration_minutes"] >= 0


# =====================================================================
# 链路2: 取消流程 — 建单 → 取消 → 同 connector 可重下
# =====================================================================

class TestCancelFlow:
    def test_cancel_then_recreate_same_connector(self, client, c_user, station_and_device):
        """§7.5 取消后 connector 释放 → 同一 connector 可重新建单 (201)。"""
        u, token = c_user
        st, dev = station_and_device

        created = _create_order(client, token, st.id, dev.id, connector_id=1)
        order_no = created["order_id"]

        # 取消
        r = client.post(f"{ORDERS}/{order_no}/cancel", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["order_status"] == "cancelled"

        # 同 connector 重下: connector 不再被活跃订单占用 → 成功
        again = _create_order(client, token, st.id, dev.id, connector_id=1)
        assert again["order_status"] == "pending"
        assert again["connector_id"] == 1
        assert again["order_id"] != order_no  # 新订单号


# =====================================================================
# 链路3: 互斥 — 已有活跃订单的 connector 再建 → 业务错误
# =====================================================================

class TestConnectorMutex:
    def test_active_order_blocks_recreate(self, client, station_and_device):
        """§7.1: 同 device+connector 已有活跃订单 → CONNECTOR_BUSY (业务错误)。

        注: C 端契约 §6 统一 code=0, 业务错误为 HTTP 200 + code!=0 + message,
        非 HTTP 409 (与 RESTful 管理端语义区分)。
        """
        st, dev = station_and_device
        # 用户 A 正在该 connector 充电
        a = _add_user(client._sesh, f"owner_{uuid.uuid4().hex[:6]}")
        ta = _login_token(client, a.username)
        _create_order(client, ta, st.id, dev.id, connector_id=2)
        # 推进到 charging, 锁定 connector
        s = client._sesh
        s.query(ChargingOrder).filter(
            ChargingOrder.user_id == a.id, ChargingOrder.connector_id == 2
        ).update({ChargingOrder.order_status: OrderStatus.CHARGING}, synchronize_session=False)
        s.commit()

        # 用户 B 同 connector 建单 → CONNECTOR_BUSY
        b = _add_user(client._sesh, f"other_{uuid.uuid4().hex[:6]}")
        tb = _login_token(client, b.username)
        r = client.post(
            ORDERS,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 2},
            headers=_auth(tb),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert "CONNECTOR_BUSY" in body["message"]

        # 不同 connector 仍可用
        ok = _create_order(client, tb, st.id, dev.id, connector_id=1)
        assert ok["order_status"] == "pending"


# =====================================================================
# 链路4: 跨模块 — 充电完成 → 提交开票申请 → 查开票列表 (§7 + §5)
# =====================================================================

class TestChargingToInvoice:
    def test_completed_order_can_request_invoice(self, client, c_user, station_and_device):
        """§7(充电完成 PAID) + §5.1(开票申请) + §5.2(列表) 串联。

        发票申请校验: 订单 payment_status=PAID 且 paid_amount 非空 (见
        invoice_request_service.apply_invoice)。
        """
        u, token = c_user
        st, dev = station_and_device

        # 建单并完成 + 标记已支付 (模拟支付回调: completed + PAID)
        created = _create_order(client, token, st.id, dev.id, connector_id=1)
        order_no = created["order_id"]
        s = client._sesh
        order = s.query(ChargingOrder).filter(ChargingOrder.order_no == order_no).one()
        order.order_status = OrderStatus.COMPLETED
        order.payment_status = OrderPaymentStatus.PAID
        order.payment_method = PaymentMethod.WECHAT
        order.total_amount = Decimal("35.25")
        order.paid_amount = Decimal("35.25")
        s.commit()

        # §5.1 提交开票申请
        r = client.post(
            INVOICES,
            json={
                "order_ids": [order_no],
                "title_type": "personal",
                "title_name": "张三",
            },
            headers=_auth(token),
        )
        assert r.status_code == 202, r.text
        inv = r.json()["data"]
        assert inv["status"] == "pending"
        assert inv["amount"] == 3525  # 元→分

        # §5.2 列表能看到这条申请
        r = client.get(INVOICES, headers=_auth(token))
        assert r.status_code == 200, r.text
        items = r.json()["data"]["items"]
        assert any(i["invoice_id"] == inv["invoice_id"] for i in items)

    def test_unpaid_order_cannot_request_invoice(self, client, c_user, station_and_device):
        """§5.1 守卫: 未支付订单不可开票 → code!=0 ORDER_NOT_PAID
        (卡 418a675a: 业务错误统一 biz_error, InvoiceError 带 reason)。"""
        u, token = c_user
        st, dev = station_and_device
        created = _create_order(client, token, st.id, dev.id, connector_id=1)
        order_no = created["order_id"]  # 仍 unpaid

        r = client.post(
            INVOICES,
            json={"order_ids": [order_no], "title_type": "personal", "title_name": "张三"},
            headers=_auth(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_PAID"
        assert body["data"] is None


# =====================================================================
# 链路5: 权限隔离 — 用户 A 的订单用户 B 不可见/不可操作 → 404
# =====================================================================

class TestPermissionIsolation:
    def test_other_user_cannot_view_or_operate(self, client, station_and_device):
        """§7 安全: 订单对非本人返回 404 (不泄露存在); status/stop/cancel/detail 均隔离。"""
        st, dev = station_and_device
        owner = _add_user(client._sesh, f"owner_{uuid.uuid4().hex[:6]}")
        intruder = _add_user(client._sesh, f"intruder_{uuid.uuid4().hex[:6]}")
        token_owner = _login_token(client, owner.username)
        token_intruder = _login_token(client, intruder.username)

        # owner 建单 + 推进到 charging
        created = _create_order(client, token_owner, st.id, dev.id, connector_id=1)
        order_no = created["order_id"]
        s = client._sesh
        s.query(ChargingOrder).filter(ChargingOrder.order_no == order_no).update(
            {ChargingOrder.order_status: OrderStatus.CHARGING,
             ChargingOrder.user_id: owner.id},
            synchronize_session=False,
        )
        s.commit()

        h = _auth(token_intruder)
        # 查状态 → code!=0 ORDER_NOT_FOUND (卡 418a675a: 业务错误统一 biz_error)
        for probe, r0 in [
            ("status", client.get(f"{ORDERS}/{order_no}/status", headers=h)),
            ("stop", client.post(f"{ORDERS}/{order_no}/stop", headers=h)),
            ("cancel", client.post(f"{ORDERS}/{order_no}/cancel", headers=h)),
            ("detail", client.get(f"{ORDERS}/{order_no}?detail=full", headers=h)),
        ]:
            assert r0.status_code == 200, probe
            body = r0.json()
            assert body["code"] != 0, probe
            assert body["message"] == "ORDER_NOT_FOUND", probe
            assert body["data"] is None, probe
        # 列表只返回 intruder 自己的 (空)
        r = client.get(ORDERS, headers=h)
        assert r.json()["data"]["total"] == 0

    def test_invoice_isolated_by_user(self, client, station_and_device):
        """§5 权限: 用户 A 的开票申请用户 B 看不到, 也不可用 A 的订单号申请。"""
        st, dev = station_and_device
        owner = _add_user(client._sesh, f"own_{uuid.uuid4().hex[:6]}")
        intruder = _add_user(client._sesh, f"int_{uuid.uuid4().hex[:6]}")
        token_owner = _login_token(client, owner.username)
        token_intruder = _login_token(client, intruder.username)

        # owner 完成一笔 PAID 订单
        created = _create_order(client, token_owner, st.id, dev.id, connector_id=1)
        order_no = created["order_id"]
        s = client._sesh
        s.query(ChargingOrder).filter(ChargingOrder.order_no == order_no).update(
            {ChargingOrder.order_status: OrderStatus.COMPLETED,
             ChargingOrder.payment_status: OrderPaymentStatus.PAID,
             ChargingOrder.total_amount: Decimal("10.00"),
             ChargingOrder.paid_amount: Decimal("10.00")},
            synchronize_session=False,
        )
        s.commit()

        # owner 申请开票
        r = client.post(
            INVOICES,
            json={"order_ids": [order_no], "title_type": "personal", "title_name": "A"},
            headers=_auth(token_owner),
        )
        assert r.status_code == 202
        owner_inv_id = r.json()["data"]["invoice_id"]

        # intruder 列表看不到 owner 的申请
        r = client.get(INVOICES, headers=_auth(token_intruder))
        assert all(i["invoice_id"] != owner_inv_id for i in r.json()["data"]["items"])

        # intruder 用 owner 的订单号申请 → 订单非本人 → code!=0 ORDER_NOT_FOUND
        # (service: user_id != user.id; 卡 418a675a 统一 biz_error)
        r = client.post(
            INVOICES,
            json={"order_ids": [order_no], "title_type": "personal", "title_name": "B"},
            headers=_auth(token_intruder),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"


# =====================================================================
# Part1 验证: order_no 并发竞态重试 (方案C)
# 单线程无法自然触发并发碰撞, 用 monkeypatch 模拟首次 flush 撞唯一约束,
# 验证 _persist_order 换序号重试成功; 以及连续超限抛 500。
# =====================================================================

class TestOrderNoConcurrencyRetry:
    """order_no 并发竞态重试 (方案C, Part1)。

    单线程无法自然复现「两事务同读旧 count → 同序号 INSERT 撞唯一约束」,
    故对 _persist_order 做单元级验证: 先 seed 占住候选序号的订单 (真实唯一约束),
    再 patch count 查询返回偏小值 (模拟并发读到旧 count), 让预估序号撞上已存订单,
    验证 savepoint 回滚 + 序号递增重试成功; 以及超限抛 500。
    """

    def _seed_order(self, session, order_no):
        o = ChargingOrder(
            order_no=order_no,
            station_id=1, device_id=1, user_id=1,
            user_type=UserType.APP, connector_id=1,
            order_status=OrderStatus.CANCELLED,  # 非活跃, 不干扰业务校验
            payment_status=OrderPaymentStatus.UNPAID,
        )
        session.add(o)
        session.commit()

    def _patch_count(self, session, monkeypatch, value):
        """让 session.query(...).filter(...).count() 返回 value (模拟并发旧读)。"""
        orig_query = session.query

        class _Q:
            def __init__(self, q):
                self._q = q
            def filter(self, *a, **kw):
                self._q = self._q.filter(*a, **kw)
                return self
            def count(self):
                return value

        monkeypatch.setattr(session, "query", lambda *a, **kw: _Q(orig_query(*a, **kw)))

    def _build(self, order_no):
        return ChargingOrder(
            order_no=order_no,
            station_id=1, device_id=1, user_id=1,
            user_type=UserType.APP, connector_id=1,
            order_status=OrderStatus.PENDING,
            payment_status=OrderPaymentStatus.UNPAID,
        )

    def test_retry_on_collision_succeeds(self, client, monkeypatch):
        """预估序号撞已存订单 → savepoint 回滚 + 序号+1 重试成功 (002)。"""
        s = client._sesh
        monkeypatch.setattr(business_orders, "_order_no_prefix", lambda: ("TLFIXED", 1))
        # 占住首个候选序号 (并发对手已抢先生成 001)
        self._seed_order(s, "TLFIXED001")
        # 模拟并发旧读: count=0 → 预估 001 → INSERT 撞 seed → 重试 002 成功
        self._patch_count(s, monkeypatch, 0)

        order = business_orders._persist_order(s, self._build)
        assert order.order_no == "TLFIXED002"

    def test_retry_exhausted_returns_500(self, client, monkeypatch):
        """所有候选序号均被占 → 超过 _ORDER_NO_RETRY → 抛 500。"""
        s = client._sesh
        monkeypatch.setattr(business_orders, "_order_no_prefix", lambda: ("TLFIXED", 1))
        # 占住全部 5 个候选序号 (001..005)
        for i in range(1, business_orders._ORDER_NO_RETRY + 1):
            self._seed_order(s, f"TLFIXED{i:03d}")
        # 旧读 count=0 → 预估 001..005 逐一撞约束 → 全部重试耗尽
        self._patch_count(s, monkeypatch, 0)

        with pytest.raises(HTTPException) as exc:
            business_orders._persist_order(s, self._build)
        assert exc.value.status_code == 500
