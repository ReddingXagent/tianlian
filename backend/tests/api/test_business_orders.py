"""充电生命周期 API 测试 (用户端云端契约 §7, 卡 0a080df5)

覆盖 app/api/v1/business_orders.py (挂 /api/v1/business 前缀):
- POST /business/orders                  创建充电订单 (校验 connector 可用 + 无未完成订单 → 201)
- POST /business/orders/{order_id}/stop  停止充电 (OCPP StopTransaction mock → completed)
- GET  /business/orders/{order_id}/status 实时状态 (充电中/完成)
- GET  /business/orders                  用户订单列表 (分页 + status/station/日期过滤)
- POST /business/orders/{order_id}/cancel 取消订单 (仅 pending)
- GET  /business/orders/{order_id}       完整明细 (§7.7, ?detail=full; 兼容 §2.3 轻量)

C 端用户契约统一 code=0。认证 get_current_user, 用 VIEWER 模拟 C 端用户。
金额单位: 响应里是分(整数); 模型存储是元(Decimal)。
"""
import uuid
from datetime import datetime, timezone, timedelta, time
from decimal import Decimal

import bcrypt
import pytest

from app.models.charging_order import (
    ChargingOrder,
    OrderPaymentStatus,
    OrderStatus,
    PaymentMethod,
    UserType,
)
from app.models.device import Device, DeviceStatus, DeviceType
from app.models.enterprise import Enterprise, EnterpriseStatus
from app.models.enterprise_vehicle import EnterpriseVehicle
from app.models.pricing_v2 import EnergyPrice, PeriodType, TimeSlotDefinition
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

BASE = "/api/v1/business/orders"


# ─── helpers ───

def _add_user(session, username, role=UserRole.VIEWER, team_id=None, password="pw123456"):
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


def _seed_station(session, *, name="甘天地光储充示范站"):
    st = Station(
        name=name,
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址",
        status=StationStatus.NORMAL,
    )
    session.add(st)
    session.commit()
    session.refresh(st)
    return st


def _seed_device(session, *, station_id, status=DeviceStatus.ONLINE, code=None):
    dev = Device(
        sn=f"SN{uuid.uuid4().hex[:10]}",
        name="充电桩",
        code=code or f"CHG{uuid.uuid4().hex[:6].upper()}",
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


def _seed_order(
    session,
    *,
    user_id,
    station_id,
    device_id,
    connector_id=1,
    order_status=OrderStatus.PENDING,
    payment_status=OrderPaymentStatus.UNPAID,
    order_no=None,
    charged_kwh=Decimal("0.00"),
    total_amount=Decimal("0.00"),
    start_time=None,
    plate_number=None,
):
    o = ChargingOrder(
        order_no=order_no or f"TL{uuid.uuid4().hex[:14].upper()}",
        station_id=station_id,
        device_id=device_id,
        user_id=user_id,
        user_type=UserType.APP,
        connector_id=connector_id,
        plate_number=plate_number,
        order_status=order_status,
        payment_status=payment_status,
        charged_kwh=charged_kwh,
        total_amount=total_amount,
        start_time=start_time,
    )
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


def _seed_enterprise(session, *, name="测试车队", balance=Decimal("10000.00"),
                     credit_limit=Decimal("0.00")):
    ent = Enterprise(
        name=name,
        code=f"ENT{uuid.uuid4().hex[:8].upper()}",
        balance=balance,
        credit_limit=credit_limit,
        status=EnterpriseStatus.ACTIVE,
    )
    session.add(ent)
    session.commit()
    session.refresh(ent)
    return ent


def _seed_enterprise_vehicle(session, *, enterprise_id, plate_number):
    """绑定车牌 → 企业 (approval_status=confirmed 才算正式入队)。"""
    ev = EnterpriseVehicle(
        enterprise_id=enterprise_id,
        plate_number=plate_number,
        vin=f"VIN{uuid.uuid4().hex[:14].upper()}",
        approval_status="confirmed",
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return ev


def _seed_tou_pricing(session, *, station_id, price_per_kwh):
    """为站点 seed 一个全天覆盖的时段 + 对应 EnergyPrice。

    start==end==00:00 在 _slot_window_local 语义里是「全天窗口」, 任何墙钟时刻都命中,
    也避开 now±2h 构造窗口在东八区 00:00-02:00 运行时跨午夜 (start 落到「昨天」的
    time, 被实现按跨午夜时段解释成 [今天 start, 明天 end), 当前时刻反而落不进窗口)
    导致的降级默认费率误判 (卡 4223a9d5)。
    effective_date=今天, 无 expire_date, is_active=True。
    """
    from app.api.v1.business_orders import _CN_TZ

    now = datetime.now(_CN_TZ)
    start_t = time(0, 0)
    end_t = time(0, 0)
    slot = TimeSlotDefinition(
        name="测试峰",
        period_type=PeriodType.PEAK,
        start_time=start_t,
        end_time=end_t,
        is_active=True,
    )
    session.add(slot)
    session.commit()
    session.refresh(slot)
    ep = EnergyPrice(
        station_id=station_id,
        slot_id=slot.id,
        price_per_kwh=Decimal(str(price_per_kwh)),
        effective_date=now.date(),
        expire_date=None,
        is_active=True,
    )
    session.add(ep)
    session.commit()
    return slot, ep


@pytest.fixture
def c_user(client):
    """C 端用户 (VIEWER) + 其登录 token。"""
    u = _add_user(client._sesh, f"appuser_{uuid.uuid4().hex[:6]}")
    token = _login_token(client, u.username)
    return u, token


@pytest.fixture
def station_and_device(client):
    st = _seed_station(client._sesh)
    dev = _seed_device(client._sesh, station_id=st.id)
    return st, dev


# =====================================================================
# §7.1 POST /business/orders — 创建充电订单
# =====================================================================

class TestCreateOrder:
    def test_create_ok(self, client, c_user, station_and_device):
        """正常创建: connector 可用 + 无未完成订单 → 201 + pending。"""
        u, token = c_user
        st, dev = station_and_device
        r = client.post(
            BASE,
            json={
                "station_id": st.id,
                "device_id": dev.id,
                "connector_id": 1,
                "user_type": "app",
            },
            headers=_auth(token),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["order_status"] == "pending"
        assert data["payment_status"] == "unpaid"
        assert data["station_id"] == st.id
        assert data["device_id"] == dev.id
        assert data["connector_id"] == 1
        # 订单号格式 TL + 14位时间戳 + 3位序号
        assert data["order_id"].startswith("TL")
        assert len(data["order_id"]) == 19  # TL(2) + 14 + 3
        assert "created_at" in data and data["created_at"]

    def test_create_connector_busy(self, client, c_user, station_and_device):
        """同 connector 已有 charging 订单 → CONNECTOR_BUSY (code=1)。"""
        u, token = c_user
        st, dev = station_and_device
        # 另一个用户正在该 connector 充电
        other = _add_user(client._sesh, f"other_{uuid.uuid4().hex[:6]}")
        _seed_order(
            client._sesh,
            user_id=other.id,
            station_id=st.id,
            device_id=dev.id,
            connector_id=1,
            order_status=OrderStatus.CHARGING,
        )
        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
            headers=_auth(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert "CONNECTOR_BUSY" in body["message"]

    def test_create_existing_order(self, client, c_user, station_and_device):
        """用户已有未完成订单 (pending) → EXISTING_ORDER。"""
        u, token = c_user
        st, dev = station_and_device
        _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            connector_id=1,
            order_status=OrderStatus.PENDING,
        )
        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 2},
            headers=_auth(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert "EXISTING_ORDER" in body["message"]

    def test_create_cancels_stale_pending_then_ok(self, client, c_user, station_and_device):
        """防御 (卡 6ff02fd2): 用户有 pending 超时 (>10min) 旧单 → 自动取消旧单 + 建新单 201。"""
        u, token = c_user
        st, dev = station_and_device
        stale = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            connector_id=1,
            order_status=OrderStatus.PENDING,
        )
        # 把 created_at 推到 11 分钟前, 触发超时判定
        stale.created_at = datetime.now(timezone.utc) - timedelta(minutes=11)
        client._sesh.commit()

        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 2},
            headers=_auth(token),
        )
        # 旧僵尸单已清理 → 放行建新单
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["order_status"] == "pending"
        # 旧单被标记 cancelled
        client._sesh.expire_all()
        old = (
            client._sesh.query(ChargingOrder)
            .filter_by(order_no=stale.order_no)
            .one()
        )
        assert old.order_status == OrderStatus.CANCELLED

    def test_create_keeps_fresh_pending_existing(self, client, c_user, station_and_device):
        """防御边界: 用户 pending 未超时 (<10min) → 仍返回 EXISTING_ORDER, 不取消。"""
        u, token = c_user
        st, dev = station_and_device
        _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            connector_id=1,
            order_status=OrderStatus.PENDING,  # created_at = now, 未超时
        )
        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 2},
            headers=_auth(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert "EXISTING_ORDER" in body["message"]

    def test_create_offline_device(self, client, c_user, station_and_device):
        """设备离线 → OFFLINE。"""
        u, token = c_user
        st, dev = station_and_device
        dev.status = DeviceStatus.OFFLINE
        client._sesh.commit()
        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
            headers=_auth(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert "OFFLINE" in body["message"]

    def test_create_order_fault_device_returns_fault_error(self, client, c_user, station_and_device):
        """设备 FAULT 故障 → code=1 message=FAULT (不是 OFFLINE)。

        _ocpp_remote_start 会拒绝 FAULT 设备, 错误码应反映真实原因 FAULT,
        而非误报 OFFLINE (卡 a319f721 Bug1)。
        """
        u, token = c_user
        st, dev = station_and_device
        dev.status = DeviceStatus.FAULT
        client._sesh.commit()
        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
            headers=_auth(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "FAULT"

    def test_create_order_connector_race_second_check(self, client, c_user, station_and_device, monkeypatch):
        """connector 占用 TOCTOU 并发二次检查 (卡 a319f721 Bug3)。

        模拟 check-then-act 窗口: 另一请求已在同 connector 建单, 但首次 busy 查询
        "漏看" (返回 None)。此时若无二次检查, 当前请求会建单成功 (重复占用同一枪);
        加了二次检查应回滚并返回 CONNECTOR_BUSY。
        """
        from app.api.v1 import business_orders

        u, token = c_user
        st, dev = station_and_device
        # 先在同 device+connector 插入一条 active 订单 (另一请求的成果)
        other = _add_user(client._sesh, f"other_{uuid.uuid4().hex[:6]}")
        _seed_order(
            client._sesh,
            user_id=other.id,
            station_id=st.id,
            device_id=dev.id,
            connector_id=1,
            order_status=OrderStatus.CHARGING,
        )

        real_query = client._sesh.query

        def _first_busy_blind(db_self):
            """首次 busy 查询 (check 阶段) 看不到已占用 → 模拟竞态窗口。"""
            q = real_query(ChargingOrder)
            return q

        # 仅让 create_order 内的首次 busy 查询返回空: 通过给 Session.query 打桩,
        # 第一次查 ChargingOrder 返回 None (check 通过), 后续查照常。
        call_state = {"busy_queries": 0}
        orig_query = type(client._sesh).query

        def patched_query(self, *entities, **kwargs):
            # 识别 create_order 里的 busy 查询: 过滤 ChargingOrder + order_status in active
            if entities and entities[0] is ChargingOrder:
                call_state["busy_queries"] += 1
                q = orig_query(self, *entities, **kwargs)
                # 首次 (check 阶段) 屏蔽占用订单 → 返回空集
                if call_state["busy_queries"] == 1:
                    return q.filter(ChargingOrder.id == -1)
                return q
            return orig_query(self, *entities, **kwargs)

        monkeypatch.setattr(type(client._sesh), "query", patched_query)

        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
            headers=_auth(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0, f"竞态二次检查应拦截 → {body}"
        assert "CONNECTOR_BUSY" in body["message"]

    def test_create_order_persist_integrity_error_returns_connector_busy(
        self, client, c_user, station_and_device, monkeypatch
    ):
        """_persist_order INSERT 撞 partial unique index → CONNECTOR_BUSY (DB 级兜底)。

        模拟并发竞态落点: check-then-act 窗口内另一请求已抢先在同 connector 建单,
        本请求的 INSERT 撞 uq_connector_active_order partial unique index 抛
        IntegrityError。create_order 必须 catch 并返回 code!=0 CONNECTOR_BUSY, 而非裸 500。
        (应用层二次检查 busy2 在 SQLite 单 writer 下不真并发, DB 约束才是硬兜底 — 卡 d9bba836)
        """
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        from app.api.v1 import business_orders

        u, token = c_user
        st, dev = station_and_device

        def _boom(db, build_order):
            raise SAIntegrityError("simulated partial index conflict", {}, Exception())

        monkeypatch.setattr(business_orders, "_persist_order", _boom)

        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
            headers=_auth(token),
        )
        assert r.status_code == 200, f"竞态应返回业务错误非异常 → {r.text[:300]}"
        body = r.json()
        assert body["code"] != 0, f"IntegrityError 应转 CONNECTOR_BUSY → {body}"
        assert "CONNECTOR_BUSY" in body["message"]

    def test_create_order_partial_unique_index_blocks_duplicate_active(
        self, client, c_user, station_and_device, monkeypatch
    ):
        """partial unique index 真实拦截同 device+connector 的第二条活跃订单 (卡 d9bba836)。

        端到端验证 DB 约束: 让 create_order 的首次 busy 查询"漏看"(模拟竞态窗口,
        另一请求的 active 订单此刻已存在但本请求读到旧快照), 随后 INSERT 直接撞
        uq_connector_active_order。SQLite ≥3.8 支持 partial index, 此处应被约束拦下;
        若环境 partial index 不生效, 该测试断言 DB 拦截失败会暴露(届时改为依赖 catch 逻辑)。
        """
        u, token = c_user
        st, dev = station_and_device
        # 另一请求已抢先在同 connector 建一条 active 订单
        other = _add_user(client._sesh, f"other_{uuid.uuid4().hex[:6]}")
        _seed_order(
            client._sesh,
            user_id=other.id,
            station_id=st.id,
            device_id=dev.id,
            connector_id=1,
            order_status=OrderStatus.CHARGING,
        )

        orig_query = type(client._sesh).query
        call_state = {"charging_queries": 0}

        def patched_query(self, *entities, **kwargs):
            # 屏蔽 create_order 内首次 busy 查询 → 模拟竞态窗口(check 通过)
            if entities and entities[0] is ChargingOrder:
                call_state["charging_queries"] += 1
                q = orig_query(self, *entities, **kwargs)
                if call_state["charging_queries"] == 1:
                    return q.filter(ChargingOrder.id == -1)
            return orig_query(self, *entities, **kwargs)

        monkeypatch.setattr(type(client._sesh), "query", patched_query)

        r = client.post(
            BASE,
            json={"station_id": st.id, "device_id": dev.id, "connector_id": 1},
            headers=_auth(token),
        )
        assert r.status_code == 200, f"竞态应返回业务错误 → {r.text[:300]}"
        body = r.json()
        # DB 级 partial index 拦截 或 应用层二次检查任一生效即可
        assert body["code"] != 0, f"重复活跃订单应被拦截 → {body}"
        assert "CONNECTOR_BUSY" in body["message"]

    def test_create_invalid_station(self, client, c_user):
        """无效 station_id → code!=0 STATION_NOT_FOUND (卡 418a675a)。"""
        u, token = c_user
        r = client.post(
            BASE,
            json={"station_id": 999999, "device_id": 1, "connector_id": 1},
            headers=_auth(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "STATION_NOT_FOUND"
        assert body["data"] is None

    def test_create_invalid_device(self, client, c_user, station_and_device):
        """station 存在但 device_id 无效/不属于该站 → code!=0 DEVICE_NOT_FOUND。"""
        u, token = c_user
        r = client.post(
            BASE,
            json={"station_id": station_and_device[0].id, "device_id": 999999, "connector_id": 1},
            headers=_auth(token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "DEVICE_NOT_FOUND"
        assert body["data"] is None

    def test_create_no_auth(self, anon_client):
        """无认证 → 401。"""
        r = anon_client.post(BASE, json={"station_id": 1, "device_id": 1, "connector_id": 1})
        assert r.status_code == 401


# =====================================================================
# §7.2 POST /business/orders/{order_id}/stop — 停止充电
# =====================================================================

class TestStopOrder:
    def test_stop_ok(self, client, c_user, station_and_device):
        """charging → completed: OCPP StopTransaction mock + 费用计算。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=Decimal("23.50"),
            start_time=datetime.now(timezone.utc) - timedelta(minutes=45),
        )
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["order_id"] == o.order_no
        assert data["order_status"] == "completed"
        assert data["charged_kwh"] == 23.50
        assert data["duration_minutes"] >= 0
        assert data["total_amount"] >= 0  # 分
        assert data["stop_reason"] == "user_manual"

    def test_stop_not_charging(self, client, c_user, station_and_device):
        """非 charging 状态停止 → ORDER_NOT_CHARGING。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.PENDING,
        )
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert "ORDER_NOT_CHARGING" in body["message"]

    def test_stop_idempotent(self, client, c_user, station_and_device):
        """重复停止: 已 completed → 返回当前状态, 不重复下发。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=Decimal("10.00"),
        )
        r1 = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r1.json()["data"]["order_status"] == "completed"
        r2 = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        # 幂等: 仍返回 completed (不报错)
        body = r2.json()
        assert body["code"] == 0
        assert body["data"]["order_status"] == "completed"

    def test_stop_not_found(self, client, c_user):
        u, token = c_user
        r = client.post(f"{BASE}/NOPE/stop", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None

    def test_stop_other_user_order(self, client, station_and_device):
        """非本人订单 → code!=0 ORDER_NOT_FOUND (不泄露存在)。"""
        st, dev = station_and_device
        owner = _add_user(client._sesh, f"owner_{uuid.uuid4().hex[:6]}")
        intruder = _add_user(client._sesh, f"intruder_{uuid.uuid4().hex[:6]}")
        o = _seed_order(
            client._sesh,
            user_id=owner.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
        )
        token = _login_token(client, intruder.username)
        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None

    # ─── 契约 §7.6 企业/车队余额自动扣款 (卡 42ccb1a5) ───

    def test_stop_enterprise_auto_deduct(self, client, c_user, station_and_device):
        """企业用户余额充足: stop 完成 → 余额自动扣款, payment_status=paid + method=enterprise。"""
        u, token = c_user
        st, dev = station_and_device
        plate = f"京A{uuid.uuid4().hex[:5].upper()}"
        ent = _seed_enterprise(client._sesh, balance=Decimal("10000.00"))
        _seed_enterprise_vehicle(client._sesh, enterprise_id=ent.id, plate_number=plate)
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=Decimal("23.50"),
            plate_number=plate,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=45),
        )
        o.paid_amount = Decimal("35.25")
        o.total_amount = Decimal("35.25")
        client._sesh.commit()

        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["order_status"] == "completed"

        # 落库: payment_status=paid, method=enterprise
        client._sesh.expire_all()
        done = client._sesh.query(ChargingOrder).filter_by(order_no=o.order_no).one()
        assert done.payment_status == OrderPaymentStatus.PAID
        assert done.payment_method == PaymentMethod.ENTERPRISE
        # 余额已扣减
        client._sesh.expire_all()
        ent_after = client._sesh.query(Enterprise).filter_by(id=ent.id).one()
        assert ent_after.balance == Decimal("10000.00") - Decimal("35.25")

    def test_stop_enterprise_insufficient_balance(self, client, c_user, station_and_device):
        """企业用户余额不足: stop 完成 → 保持 unpaid (不扣款不报错), 用户可走IM-B支付。"""
        u, token = c_user
        st, dev = station_and_device
        plate = f"京B{uuid.uuid4().hex[:5].upper()}"
        # 余额 1 元, 信用额度 0 → 扣 35.25 必透支
        ent = _seed_enterprise(client._sesh, balance=Decimal("1.00"), credit_limit=Decimal("0.00"))
        _seed_enterprise_vehicle(client._sesh, enterprise_id=ent.id, plate_number=plate)
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=Decimal("23.50"),
            plate_number=plate,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=45),
        )
        o.paid_amount = Decimal("35.25")
        o.total_amount = Decimal("35.25")
        client._sesh.commit()

        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        # 不报错: 仍正常完成订单
        assert r.status_code == 200, r.text
        assert r.json()["data"]["order_status"] == "completed"

        client._sesh.expire_all()
        done = client._sesh.query(ChargingOrder).filter_by(order_no=o.order_no).one()
        assert done.payment_status == OrderPaymentStatus.UNPAID
        # 余额未被扣减
        client._sesh.expire_all()
        ent_after = client._sesh.query(Enterprise).filter_by(id=ent.id).one()
        assert ent_after.balance == Decimal("1.00")

    def test_stop_normal_user_unpaid(self, client, c_user, station_and_device):
        """普通用户 (车牌未关联企业): stop 完成 → 保持 unpaid (现有行为不变)。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=Decimal("23.50"),
            plate_number=f"京C{uuid.uuid4().hex[:5].upper()}",  # 无人关联
            start_time=datetime.now(timezone.utc) - timedelta(minutes=45),
        )
        o.paid_amount = Decimal("35.25")
        o.total_amount = Decimal("35.25")
        client._sesh.commit()

        r = client.post(f"{BASE}/{o.order_no}/stop", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["order_status"] == "completed"

        client._sesh.expire_all()
        done = client._sesh.query(ChargingOrder).filter_by(order_no=o.order_no).one()
        assert done.payment_status == OrderPaymentStatus.UNPAID


# =====================================================================
# §7.3 GET /business/orders/{order_id}/status — 实时状态
# =====================================================================

class TestOrderStatus:
    def test_status_charging(self, client, c_user, station_and_device):
        """充电中: 返回 charged_kwh/soc/power/estimated_cost。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=Decimal("12.30"),
            start_time=datetime.now(timezone.utc) - timedelta(minutes=23),
        )
        o.start_soc = Decimal("35.0")
        client._sesh.commit()
        r = client.get(f"{BASE}/{o.order_no}/status", headers=_auth(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["order_status"] == "charging"
        assert data["charged_kwh"] == 12.30
        assert data["start_soc"] == 35.0
        assert "estimated_cost" in data
        assert "duration_minutes" in data

    def test_status_estimated_cost_uses_tou_price(self, client, c_user, station_and_device):
        """契约 §7.3: estimated_cost = 已充电量 × 当前时段单价(分)。

        seed 站点 TOU 定价(覆盖当前时刻) → 按真实时段电价计算, 不再用硬编码 0.8。
        """
        u, token = c_user
        st, dev = station_and_device
        _seed_tou_pricing(client._sesh, station_id=st.id, price_per_kwh="1.25")
        kwh = Decimal("12.30")
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=kwh,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        r = client.get(f"{BASE}/{o.order_no}/status", headers=_auth(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        # 12.30 kWh × 1.25 元/kWh × 100 = 1537.5 → 四舍五入 1538 分
        assert data["estimated_cost"] == int(round(float(kwh) * 1.25 * 100))
        assert data["estimated_cost"] != int(round(float(kwh) * 0.8 * 100))

    def test_status_estimated_cost_fallback_default(self, client, c_user, station_and_device):
        """无 TOU 定价配置 → 降级默认费率 1.0 元/kWh, 不报错 (契约 §7.3)。"""
        u, token = c_user
        st, dev = station_and_device
        kwh = Decimal("20.00")
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.CHARGING,
            charged_kwh=kwh,
            start_time=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        r = client.get(f"{BASE}/{o.order_no}/status", headers=_auth(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        # 20.00 kWh × 1.0 元/kWh × 100 = 2000 分
        assert data["estimated_cost"] == 2000

    def test_status_completed(self, client, c_user, station_and_device):
        """完成订单查询状态: power_kw 为 null。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            order_status=OrderStatus.COMPLETED,
            charged_kwh=Decimal("23.50"),
        )
        r = client.get(f"{BASE}/{o.order_no}/status", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["order_status"] == "completed"
        assert data["power_kw"] is None

    def test_status_not_found(self, client, c_user):
        u, token = c_user
        r = client.get(f"{BASE}/NOPE/status", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None


# =====================================================================
# §7.4 GET /business/orders — 用户订单列表
# =====================================================================

class TestListOrders:
    def test_list_pagination(self, client, c_user, station_and_device):
        u, token = c_user
        st, dev = station_and_device
        for _ in range(3):
            _seed_order(
                client._sesh,
                user_id=u.id,
                station_id=st.id,
                device_id=dev.id,
                order_status=OrderStatus.COMPLETED,
            )
        r = client.get(f"{BASE}?page=1&page_size=2", headers=_auth(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] == 3
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_list_status_filter(self, client, c_user, station_and_device):
        u, token = c_user
        st, dev = station_and_device
        _seed_order(client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
                    order_status=OrderStatus.COMPLETED)
        _seed_order(client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
                    order_status=OrderStatus.CANCELLED)
        r = client.get(f"{BASE}?status=completed", headers=_auth(token))
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["order_status"] == "completed"

    def test_list_station_filter(self, client, c_user):
        u, token = c_user
        st1 = _seed_station(client._sesh, name="站一")
        st2 = _seed_station(client._sesh, name="站二")
        dev1 = _seed_device(client._sesh, station_id=st1.id)
        dev2 = _seed_device(client._sesh, station_id=st2.id)
        _seed_order(client._sesh, user_id=u.id, station_id=st1.id, device_id=dev1.id)
        _seed_order(client._sesh, user_id=u.id, station_id=st2.id, device_id=dev2.id)
        r = client.get(f"{BASE}?station_id={st1.id}", headers=_auth(token))
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["station_id"] == st1.id

    def test_list_only_own_orders(self, client, station_and_device):
        """只返回当前用户的订单。"""
        st, dev = station_and_device
        a = _add_user(client._sesh, "u_a")
        b = _add_user(client._sesh, "u_b")
        # COMPLETED 状态避免 partial unique index uq_connector_active_order 冲突
        # (卡 d9bba836: 同 device+connector 不可有两条活跃订单)
        _seed_order(client._sesh, user_id=a.id, station_id=st.id, device_id=dev.id,
                    connector_id=1, order_status=OrderStatus.COMPLETED)
        _seed_order(client._sesh, user_id=b.id, station_id=st.id, device_id=dev.id,
                    connector_id=2, order_status=OrderStatus.COMPLETED)
        token = _login_token(client, a.username)
        r = client.get(BASE, headers=_auth(token))
        assert r.json()["data"]["total"] == 1

    def test_list_date_filter(self, client, c_user, station_and_device):
        """start_date/end_date 过滤 created_at。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id)
        # 强制 created_at 为昨天
        yesterday = datetime.now(timezone.utc) - timedelta(days=2)
        o.created_at = yesterday
        client._sesh.commit()
        r = client.get(f"{BASE}?start_date=2020-01-01&end_date=2020-12-31",
                       headers=_auth(token))
        assert r.json()["data"]["total"] == 0

    def test_list_date_filter_cn_tz_boundary(self, client, c_user, station_and_device,
                                             monkeypatch):
        """日期过滤以东八区当日边界为准 (卡 ff8a6255)。

        订单 created_at = UTC 2020-06-14 20:00 = 北京 2020-06-15 04:00,
        属于北京 6-15 当天。用 start_date=2020-06-15 必须命中。
        若 strptime 结果按进程本地时区(此处强制 UTC)解释, 会漏掉这条订单。
        """
        import time
        monkeypatch.setenv("TZ", "UTC")
        time.tzset()
        u, token = c_user
        st, dev = station_and_device
        # 北京 2020-06-15 04:00 -> UTC 2020-06-14 20:00
        o = _seed_order(client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id)
        o.created_at = datetime(2020, 6, 14, 20, 0, 0)
        client._sesh.commit()
        r = client.get(f"{BASE}?start_date=2020-06-15", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["total"] == 1


# =====================================================================
# §7.5 POST /business/orders/{order_id}/cancel — 取消订单
# =====================================================================

class TestCancelOrder:
    def test_cancel_pending_ok(self, client, c_user, station_and_device):
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
                        order_status=OrderStatus.PENDING)
        r = client.post(f"{BASE}/{o.order_no}/cancel", headers=_auth(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["order_id"] == o.order_no
        assert data["order_status"] == "cancelled"

    def test_cancel_charging_rejected(self, client, c_user, station_and_device):
        """非 pending 不可取消 → CANNOT_CANCEL。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id,
                        order_status=OrderStatus.CHARGING)
        r = client.post(f"{BASE}/{o.order_no}/cancel", headers=_auth(token))
        body = r.json()
        assert body["code"] != 0
        assert "CANNOT_CANCEL" in body["message"]

    def test_cancel_not_found(self, client, c_user):
        u, token = c_user
        r = client.post(f"{BASE}/NOPE/cancel", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None


# =====================================================================
# §7.7 GET /business/orders/{order_id} — 完整明细 (兼容 §2.3)
# =====================================================================

class TestOrderDetail:
    def test_detail_full(self, client, c_user, station_and_device):
        """?detail=full → §7.7 完整明细 (含费用明细, 金额分)。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(
            client._sesh,
            user_id=u.id,
            station_id=st.id,
            device_id=dev.id,
            connector_id=1,
            order_status=OrderStatus.COMPLETED,
            payment_status=OrderPaymentStatus.PAID,
            charged_kwh=Decimal("23.50"),
        )
        o.electricity_fee = Decimal("21.00")
        o.service_fee = Decimal("12.00")
        o.idle_penalty = Decimal("2.25")
        o.total_amount = Decimal("35.25")
        o.paid_amount = Decimal("35.25")
        o.payment_method = PaymentMethod.WECHAT
        o.start_soc = Decimal("35.0")
        o.end_soc = Decimal("100.0")
        o.stop_reason = "full"
        client._sesh.commit()
        r = client.get(f"{BASE}/{o.order_no}?detail=full", headers=_auth(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["order_id"] == o.order_no
        assert data["order_status"] == "completed"
        assert data["payment_status"] == "paid"
        assert data["station_name"] == st.name
        assert data["charged_kwh"] == 23.50
        # 金额为分(整数)
        assert data["electricity_fee"] == 2100
        assert data["service_fee"] == 1200
        assert data["idle_penalty"] == 225
        assert data["total_amount"] == 3525
        assert data["paid_amount"] == 3525
        assert data["payment_method"] == "im_b"
        assert data["start_soc"] == 35.0
        assert data["end_soc"] == 100.0
        assert data["stop_reason"] == "full"

    def test_detail_lightweight_compat(self, client, c_user, station_and_device):
        """不带 detail=full → §2.3 轻量查询 (仅 payment_status/transaction_id/paid_at)。
        保持向后兼容 (test_wx_merchant_payment.py 依赖此形态)。"""
        u, token = c_user
        st, dev = station_and_device
        o = _seed_order(client._sesh, user_id=u.id, station_id=st.id, device_id=dev.id)
        r = client.get(f"{BASE}/{o.order_no}", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()["data"]
        # §2.3 轻量字段集
        assert "payment_status" in data
        assert "order_id" in data

    def test_detail_not_found(self, client, c_user):
        u, token = c_user
        r = client.get(f"{BASE}/NOPE?detail=full", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["code"] != 0
        assert body["message"] == "ORDER_NOT_FOUND"
        assert body["data"] is None
